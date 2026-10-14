import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dashboard import dashboard_summary
from backend.app.api.monitoring import run_monitoring
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.transaction import Transaction
from backend.app.services.dashboard_service import DashboardService


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.reference = datetime(2025, 5, 18, 12, tzinfo=timezone.utc)
        for index, days in enumerate((0, 1, 8, 31)):
            transaction = Transaction(
                txn_date=self.reference.replace(tzinfo=None) - timedelta(days=days),
                transaction_type=("LOAD", "POS", "ATM", "POS")[index],
                amount=100.0 + index,
            )
            self.session.add(transaction)
            self.session.flush()
            if index < 3:
                self.session.add(Alert(
                    alert_code=f"ALT-R00{index + 1}-T{transaction.id:08d}",
                    rule_code=("R001", "R003", "R003")[index],
                    rule_name="Rule",
                    description="Reason",
                    transaction_id=transaction.id,
                    risk_level=("high", "medium", "medium")[index],
                    priority=index + 1,
                    status="OPEN" if index < 2 else "CLOSED",
                    created_at=self.reference - timedelta(days=days),
                ))
        self.session.commit()
        alert = self.session.query(Alert).first()
        self.session.add(Case(
            case_code="CASE-A00000001",
            alert_id=alert.id,
            status="OPEN",
            priority=1,
            created_at=self.reference,
        ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_summary_and_ranges(self):
        summary = DashboardService.summary(self.session)
        self.assertEqual(summary.transactions.total_transactions, 4)
        self.assertEqual(summary.transactions.total_transaction_amount, 406.0)
        self.assertEqual(summary.transactions.transaction_types["POS"], 2)
        self.assertEqual(summary.alerts.total_alerts, 3)
        self.assertEqual(summary.alerts.open_alerts, 2)
        self.assertEqual(summary.alerts.closed_alerts, 1)
        self.assertEqual(summary.alerts.by_rule["R003"], 2)
        self.assertEqual(summary.cases.total_cases, 1)
        self.assertEqual(summary.high_priority_alerts, 1)
        self.assertEqual(summary.high_priority_cases, 1)

        day = DashboardService.summary(
            self.session, time_range="24h", reference_time=self.reference
        )
        self.assertEqual(day.transactions.total_transactions, 2)
        week = DashboardService.summary(
            self.session, time_range="7d", reference_time=self.reference
        )
        self.assertEqual(week.transactions.total_transactions, 2)
        month = DashboardService.summary(
            self.session, time_range="30d", reference_time=self.reference
        )
        self.assertEqual(month.transactions.total_transactions, 3)

    def test_trends_top_rules_distributions_and_empty_data(self):
        alert_trend = DashboardService.trend(
            self.session, "alerts", "30d", reference_time=self.reference
        )
        transaction_trend = DashboardService.trend(
            self.session, "transactions", "30d", reference_time=self.reference
        )
        self.assertEqual(sum(point.count for point in alert_trend), 3)
        self.assertEqual(sum(point.count for point in transaction_trend), 3)
        top = DashboardService.top_rules(self.session)
        self.assertEqual(top[0].rule_code, "R003")
        self.assertEqual(top[0].alert_count, 2)

        empty_engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(empty_engine)
        empty = sessionmaker(bind=empty_engine)()
        summary = DashboardService.summary(empty)
        self.assertEqual(summary.transactions.total_transactions, 0)
        self.assertEqual(summary.alerts.total_alerts, 0)
        self.assertEqual(summary.cases.total_cases, 0)
        empty.close()
        Base.metadata.drop_all(empty_engine)
        empty_engine.dispose()

    def test_invalid_range_and_monitoring_endpoint(self):
        with self.assertRaises(ValueError):
            DashboardService.resolve_range(
                "7d", self.reference, self.reference - timedelta(days=1)
            )
        self.assertEqual(run_monitoring(db=self.session)["transactions_evaluated"], 4)
