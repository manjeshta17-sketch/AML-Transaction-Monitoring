import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.alerts import create_case_from_alert
from backend.app.api.cases import (
    add_case_comment,
    get_case,
    list_case_comments,
    update_case_status,
)
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.case_comment import CaseComment
from backend.app.models.transaction import Transaction
from backend.app.schemas.case import CaseCommentCreate, CaseStatusUpdate
from backend.app.services.case_service import CASE_STATUS_CLOSED, CASE_STATUS_IN_PROGRESS


class CaseManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def create_alert(self, priority=2):
        transaction = Transaction(
            ext_txn_id="transaction-1",
            transaction_type="LOAD",
            amount=6000,
            customer_id="customer-1",
        )
        self.session.add(transaction)
        self.session.commit()
        alert = Alert(
            alert_code=f"ALT-R001-T{transaction.id:08d}",
            rule_code="R001",
            rule_name="High-value card load",
            transaction_id=transaction.id,
            customer_id=transaction.customer_id,
            amount=transaction.amount,
            risk_level="high",
            priority=priority,
            status="OPEN",
        )
        self.session.add(alert)
        self.session.commit()
        return alert

    def create_case(self, priority=2):
        alert = self.create_alert(priority=priority)
        return create_case_from_alert(alert.id, db=self.session)

    def test_creates_a_case_from_alert_and_inherits_priority(self):
        case = self.create_case(priority=1)

        self.assertEqual(case.alert_id, 1)
        self.assertEqual(case.priority, 1)
        self.assertEqual(case.status, "OPEN")
        self.assertEqual(case.case_code, "CASE-A00000001")

    def test_prevents_duplicate_cases_for_an_alert(self):
        self.create_case()

        with self.assertRaises(HTTPException) as error:
            create_case_from_alert(1, db=self.session)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.session.query(Case).count(), 1)

    def test_status_changes_and_closing_a_case(self):
        case = self.create_case()

        in_progress = update_case_status(
            case.id,
            CaseStatusUpdate(status=CASE_STATUS_IN_PROGRESS),
            db=self.session,
        )
        self.assertEqual(in_progress.status, CASE_STATUS_IN_PROGRESS)
        self.assertIsNone(in_progress.closed_at)

        closed = update_case_status(
            case.id,
            CaseStatusUpdate(status=CASE_STATUS_CLOSED),
            db=self.session,
        )
        self.assertEqual(closed.status, CASE_STATUS_CLOSED)
        self.assertIsNotNone(closed.closed_at)

    def test_rejects_invalid_status_transitions_and_missing_cases(self):
        case = self.create_case()
        update_case_status(case.id, CaseStatusUpdate(status=CASE_STATUS_CLOSED), db=self.session)

        with self.assertRaises(HTTPException) as transition_error:
            update_case_status(
                case.id,
                CaseStatusUpdate(status=CASE_STATUS_IN_PROGRESS),
                db=self.session,
            )
        self.assertEqual(transition_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as missing_error:
            get_case(999, db=self.session)
        self.assertEqual(missing_error.exception.status_code, 404)

    def test_adds_and_retrieves_comments(self):
        case = self.create_case()

        comment = add_case_comment(
            case.id,
            CaseCommentCreate(comment="Reviewing source of funds.", created_by="analyst-1"),
            db=self.session,
        )
        comments = list_case_comments(case.id, db=self.session)

        self.assertEqual(comment.case_id, case.id)
        self.assertEqual(comment.created_by, "analyst-1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].comment, "Reviewing source of funds.")
        self.assertEqual(self.session.query(CaseComment).count(), 1)

    def test_retrieves_a_case(self):
        case = self.create_case()

        retrieved = get_case(case.id, db=self.session)
        self.assertEqual(retrieved.id, case.id)
