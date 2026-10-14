import os
import tempfile
from dataclasses import replace
from datetime import datetime
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import get_alert, list_alerts
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.services.alert_service import AlertService
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine
from backend.app.services.transaction_service import REQUIRED_COLUMNS, import_transactions


class AlertMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_transaction(self, transaction_type="LOAD", amount=6000.0):
        transaction = Transaction(
            ext_txn_id="transaction-1",
            transaction_type=transaction_type,
            amount=amount,
            customer_id="customer-1",
            card_number="4111XXXXXXXX1111",
        )
        self.session.add(transaction)
        self.session.commit()
        return transaction

    def test_creates_open_alert_with_rule_and_transaction_details(self):
        transaction = self.add_transaction()
        trigger = RuleEngine().evaluate(transaction)[0]

        alert = AlertService().create_alert(transaction, trigger, self.session)
        self.session.commit()

        self.assertEqual(alert.rule_code, "R001")
        self.assertEqual(alert.transaction_id, transaction.id)
        self.assertEqual(alert.customer_id, "customer-1")
        self.assertEqual(alert.card_number, "4111XXXXXXXX1111")
        self.assertEqual(alert.status, "OPEN")
        self.assertEqual(alert.alert_code, f"ALT-R001-T{transaction.id:08d}")

    def test_prevents_duplicate_alerts_for_the_same_transaction_and_rule(self):
        transaction = self.add_transaction()
        trigger = RuleEngine().evaluate(transaction)[0]

        self.assertIsNotNone(AlertService().create_alert(transaction, trigger, self.session))
        self.assertIsNone(AlertService().create_alert(transaction, trigger, self.session))
        self.session.commit()
        self.assertEqual(self.session.query(Alert).count(), 1)

    def test_monitoring_runs_against_imported_transactions(self):
        file_descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        os.close(file_descriptor)
        csv_path = Path(file_path)
        try:
            rows = []
            for external_id, transaction_type, amount in (
                ("load-1", "LOAD", "6000"),
                ("transfer-1", "CARD_TO_CARD", "1200"),
                ("pos-1", "POS", "9000"),
            ):
                values = {"Ext Txn Id": external_id, "TransactionType": transaction_type, "Amount": amount}
                rows.append("|".join(values.get(column, "value") for column in REQUIRED_COLUMNS))
            csv_path.write_text(
                "Transaction Report\n05/19/2025\n"
                + "|".join(REQUIRED_COLUMNS)
                + "\n"
                + "\n".join(rows)
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(import_transactions(str(csv_path), self.session), 3)
        finally:
            csv_path.unlink(missing_ok=True)

        result = MonitoringService().run(self.session)

        self.assertEqual(result.transactions_evaluated, 3)
        self.assertEqual(result.alerts_generated, 2)
        self.assertEqual(result.alerts_by_rule, {"R001": 1, "R015": 1})
        self.assertEqual(MonitoringService().run(self.session).alerts_generated, 0)

    def test_get_alerts(self):
        transaction = self.add_transaction()
        MonitoringService().run(self.session)

        alerts = list_alerts(db=self.session)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].transaction_id, transaction.id)

        detail_alert = get_alert(alerts[0].id, db=self.session)
        self.assertEqual(detail_alert.status, "OPEN")

    def test_insufficient_history_is_returned_without_creating_an_alert(self):
        historical_rule = next(rule for rule in DEFAULT_RULES if rule.rule_code == "R005")
        transaction = Transaction(
            ext_txn_id="historical-transaction-1",
            transaction_type="LOAD",
            amount=10.0,
            card_number="4111XXXXXXXX1111",
            txn_date=datetime(2025, 5, 18),
        )
        self.session.add(transaction)
        self.session.commit()

        result = MonitoringService(
            rule_engine=RuleEngine([replace(historical_rule, enabled=True)]),
        ).run(self.session)

        self.assertEqual(result.alerts_generated, 0)
        self.assertEqual(result.insufficient_history[0].rule_code, "R005")
        self.assertEqual(self.session.query(Alert).count(), 0)
