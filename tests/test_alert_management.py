import unittest
from datetime import datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import (
    create_case_from_alert,
    get_alert,
    list_alerts_endpoint,
    update_alert_assignment,
    update_alert_priority,
    update_alert_status,
)
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.schemas.alert import (
    AlertAssignmentUpdate,
    AlertPriorityUpdate,
    AlertStatusUpdate,
)


class AlertManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.alerts = []
        for index in range(5):
            transaction = Transaction(
                ext_txn_id=f"txn-{index}",
                transaction_type="LOAD",
                amount=6000 + index,
                customer_id=f"customer-{index % 2}",
                card_number="4111XXXXXXXX1111",
                txn_date=datetime(2025, 5, 1 + index),
            )
            self.session.add(transaction)
            self.session.flush()
            alert = Alert(
                alert_code=f"ALT-R00{index + 1}-T{transaction.id:08d}",
                rule_code=f"R00{index + 1}",
                rule_name="Test rule",
                description="Test reason",
                transaction_id=transaction.id,
                customer_id=transaction.customer_id,
                amount=transaction.amount,
                risk_level="high",
                priority=(index % 4) + 1,
                status="OPEN" if index < 4 else "CLOSED",
            )
            self.session.add(alert)
            self.alerts.append(alert)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_pagination_filters_sorting_and_search(self):
        page = list_alerts_endpoint(page=1, page_size=2, sort_by="priority", sort_order="desc", db=self.session)
        self.assertEqual(page.total, 5)
        self.assertEqual(page.total_pages, 3)
        self.assertEqual(len(page.alerts), 2)
        self.assertEqual(page.alerts[0].priority, 4)

        filtered = list_alerts_endpoint(rule_code="R001", db=self.session)
        self.assertEqual(filtered.total, 1)
        assigned = list_alerts_endpoint(assigned_to="analyst-1", db=self.session)
        self.assertEqual(assigned.total, 0)
        searched = list_alerts_endpoint(search="customer-1", db=self.session)
        self.assertEqual(searched.total, 2)
        by_transaction = list_alerts_endpoint(
            transaction_id=self.alerts[0].transaction_id, db=self.session
        )
        self.assertEqual(by_transaction.total, 1)

    def test_status_priority_assignment_and_updated_timestamp(self):
        alert = self.alerts[0]
        before = alert.updated_at
        update_alert_status(alert.id, AlertStatusUpdate(status="IN_PROGRESS"), self.session)
        self.session.refresh(alert)
        self.assertEqual(alert.status, "IN_PROGRESS")
        self.assertGreaterEqual(alert.updated_at, before)

        update_alert_priority(alert.id, AlertPriorityUpdate(priority=4), self.session)
        update_alert_assignment(alert.id, AlertAssignmentUpdate(assigned_to=" analyst-1 "), self.session)
        self.session.refresh(alert)
        self.assertEqual(alert.priority, 4)
        self.assertEqual(alert.assigned_to, "analyst-1")

    def test_invalid_mutations_and_filters_are_rejected(self):
        with self.assertRaises(ValidationError):
            AlertPriorityUpdate(priority=5)
        with self.assertRaises(HTTPException) as status_error:
            update_alert_status(self.alerts[0].id, AlertStatusUpdate(status="UNKNOWN"), self.session)
        self.assertEqual(status_error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as filter_error:
            list_alerts_endpoint(sort_by="not-a-column", db=self.session)
        self.assertEqual(filter_error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as date_error:
            list_alerts_endpoint(
                date_from=datetime(2025, 6, 1),
                date_to=datetime(2025, 5, 1),
                db=self.session,
            )
        self.assertEqual(date_error.exception.status_code, 422)

    def test_detail_includes_transaction_and_unknown_is_404(self):
        detail = get_alert(self.alerts[0].id, db=self.session)
        self.assertEqual(detail.transaction.transaction_type, "LOAD")
        self.assertEqual(detail.transaction.customer_id, "customer-0")
        self.assertEqual(detail.description, "Test reason")
        with self.assertRaises(HTTPException) as error:
            get_alert(99999, db=self.session)
        self.assertEqual(error.exception.status_code, 404)

    def test_case_conversion_and_duplicate_rejection_remain_intact(self):
        case = create_case_from_alert(self.alerts[0].id, db=self.session)
        self.assertEqual(case.alert_id, self.alerts[0].id)
        with self.assertRaises(HTTPException) as error:
            create_case_from_alert(self.alerts[0].id, db=self.session)
        self.assertEqual(error.exception.status_code, 409)
