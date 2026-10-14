import unittest
from datetime import datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import create_case_from_alert
from backend.app.api.cases import (
    add_case_comment,
    get_case,
    list_cases,
    list_case_comments,
    update_case_assignment,
    update_case_priority,
    update_case_status,
)
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.transaction import Transaction
from backend.app.schemas.case import (
    CaseAssignmentUpdate,
    CaseCommentCreate,
    CasePriorityUpdate,
    CaseStatusUpdate,
)
from backend.app.services.case_service import CASE_STATUS_CLOSED, CASE_STATUS_IN_PROGRESS


class CaseManagementEnhancementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        for index in range(5):
            transaction = Transaction(
                ext_txn_id=f"case-txn-{index}",
                transaction_type="LOAD",
                amount=6000 + index,
                customer_id=f"customer-{index % 2}",
                txn_date=datetime(2025, 5, 1 + index),
            )
            self.session.add(transaction)
            self.session.flush()
            alert = Alert(
                alert_code=f"ALT-R001-T{transaction.id:08d}",
                rule_code="R001",
                rule_name="High-value card load",
                description="High-value transaction",
                transaction_id=transaction.id,
                customer_id=transaction.customer_id,
                amount=transaction.amount,
                risk_level="high",
                priority=(index % 4) + 1,
                status="OPEN",
            )
            self.session.add(alert)
            self.session.flush()
            create_case_from_alert(alert.id, db=self.session)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_listing_filters_paginates_searches_and_sorts(self):
        page = list_cases(page=1, page_size=2, sort_by="priority", sort_order="desc", db=self.session)
        self.assertEqual(page.total, 5)
        self.assertEqual(page.total_pages, 3)
        self.assertEqual(len(page.cases), 2)
        self.assertEqual(page.cases[0].priority, 4)

        filtered = list_cases(priority=1, db=self.session)
        self.assertEqual(filtered.total, 2)
        searched = list_cases(search="customer-1", db=self.session)
        self.assertEqual(searched.total, 2)
        by_alert = list_cases(alert_id=1, db=self.session)
        self.assertEqual(by_alert.total, 1)

    def test_detail_includes_alert_transaction_and_comments(self):
        case_before = self.session.get(Case, 1)
        updated_before_comment = case_before.updated_at
        comment = add_case_comment(
            1,
            CaseCommentCreate(comment="Review source of funds", created_by="analyst-1"),
            db=self.session,
        )
        detail = get_case(1, db=self.session)
        self.assertEqual(detail.alert.rule_code, "R001")
        self.assertEqual(detail.transaction.transaction_type, "LOAD")
        self.assertEqual(detail.transaction.customer_id, "customer-0")
        self.assertEqual(detail.comments[0].id, comment.id)
        self.assertGreaterEqual(detail.updated_at, updated_before_comment)
        self.assertEqual(list_case_comments(1, db=self.session)[0].comment, "Review source of funds")

    def test_status_priority_assignment_and_timestamps(self):
        case = self.session.get(Case, 1)
        before = case.updated_at
        update_case_status(1, CaseStatusUpdate(status=CASE_STATUS_IN_PROGRESS), db=self.session)
        self.session.refresh(case)
        self.assertGreaterEqual(case.updated_at, before)
        update_case_priority(1, CasePriorityUpdate(priority=4), db=self.session)
        update_case_assignment(1, CaseAssignmentUpdate(assigned_to=" analyst-1 "), db=self.session)
        self.session.refresh(case)
        self.assertEqual(case.priority, 4)
        self.assertEqual(case.assigned_to, "analyst-1")
        update_case_assignment(1, CaseAssignmentUpdate(assigned_to=None), db=self.session)
        self.session.refresh(case)
        self.assertIsNone(case.assigned_to)

    def test_closing_sets_closed_at_and_invalid_values_are_rejected(self):
        update_case_status(1, CaseStatusUpdate(status=CASE_STATUS_CLOSED), db=self.session)
        case = self.session.get(Case, 1)
        self.assertIsNotNone(case.closed_at)
        with self.assertRaises(ValidationError):
            CasePriorityUpdate(priority=5)
        with self.assertRaises(HTTPException) as error:
            update_case_status(1, CaseStatusUpdate(status="UNKNOWN"), db=self.session)
        self.assertEqual(error.exception.status_code, 400)
        with self.assertRaises(ValidationError):
            CaseCommentCreate(comment="   ", created_by="analyst")

    def test_unknown_case_and_duplicate_alert_case_are_rejected(self):
        with self.assertRaises(HTTPException) as missing:
            get_case(999, db=self.session)
        self.assertEqual(missing.exception.status_code, 404)
        with self.assertRaises(HTTPException) as duplicate:
            create_case_from_alert(1, db=self.session)
        self.assertEqual(duplicate.exception.status_code, 409)
