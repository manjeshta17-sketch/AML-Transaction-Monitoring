import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.models.transaction_import import TransactionImport
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.transaction_service import (
    REQUIRED_COLUMNS,
    ImportResult,
    import_transactions,
)


class MultiFileHardeningTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.files = []

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        for path in self.files:
            path.unlink(missing_ok=True)

    def write_report(self, rows, filename):
        file_descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        os.close(file_descriptor)
        path = Path(file_path)
        self.files.append(path)
        lines = [
            "Transaction Report",
            "05/19/2025",
            "|".join(REQUIRED_COLUMNS),
        ]
        for values in rows:
            lines.append("|".join(values.get(column, "value") for column in REQUIRED_COLUMNS))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = import_transactions(
            str(path),
            self.session,
            source_filename=filename,
            detailed=True,
        )
        self.assertIsInstance(result, ImportResult)
        return result

    def row(self, external_id, transaction_type="POS", amount="50"):
        return {
            "Txn Date": "2025-05-18 23:57:23.000000",
            "Ext Txn Id": external_id,
            "Amount": amount,
            "TransactionType": transaction_type,
            "Customer Id": "customer-1",
            "Card Number": "card-1",
        }

    def test_uploads_get_distinct_import_ids_and_provenance(self):
        first = self.write_report([self.row("file-a-1")], "file-a.csv")
        second = self.write_report([self.row("file-b-1")], "file-b.csv")

        self.assertNotEqual(first.import_id, second.import_id)
        self.assertEqual(first.rows_processed, 1)
        self.assertEqual(first.records_imported, 1)
        self.assertEqual(first.duplicates_skipped, 0)
        self.assertEqual(first.status, "COMPLETED")
        imports = self.session.query(TransactionImport).order_by(TransactionImport.id).all()
        self.assertEqual([item.source_filename for item in imports], ["file-a.csv", "file-b.csv"])
        self.assertEqual(
            {transaction.import_id for transaction in self.session.query(Transaction).all()},
            {first.import_id, second.import_id},
        )

    def test_non_null_external_ids_are_idempotent_and_reported(self):
        first = self.write_report([self.row("same-id")], "file-a.csv")
        second = self.write_report([self.row("same-id")], "file-a-repeat.csv")

        self.assertEqual(first.records_imported, 1)
        self.assertEqual(second.records_imported, 0)
        self.assertEqual(second.duplicates_skipped, 1)
        self.assertEqual(self.session.query(Transaction).count(), 1)

    def test_blank_external_ids_remain_rows_and_are_not_false_deduplicated(self):
        first = self.write_report([self.row(""), self.row("")], "blank-a.csv")
        second = self.write_report([self.row(""), self.row("")], "blank-a-repeat.csv")

        self.assertEqual(first.records_imported, 2)
        self.assertEqual(second.records_imported, 2)
        self.assertEqual(second.duplicates_skipped, 0)
        self.assertEqual(self.session.query(Transaction).count(), 4)

    def test_repeated_upload_preserves_alert_and_enrichment_idempotency(self):
        self.write_report([self.row("load-1", "LOAD", "6000")], "load.csv")
        MonitoringService().run(self.session)
        self.write_report([self.row("load-1", "LOAD", "6000")], "load-repeat.csv")
        repeat_result = MonitoringService().run(self.session)

        self.assertEqual(repeat_result.alerts_generated, 0)
        self.assertEqual(self.session.query(Alert).count(), 1)
        self.assertEqual(self.session.query(TransactionAIEnrichment).count(), 1)

    def test_existing_customer_history_is_used_across_imports(self):
        start = datetime(2025, 5, 12)
        history = []
        for index in range(6):
            values = self.row(f"history-{index}", amount=str(50 + index))
            values["Txn Date"] = (start + timedelta(hours=index)).isoformat(sep=" ")
            history.append(values)
        self.write_report(history, "history.csv")
        current = self.row("current", amount="75")
        current["Txn Date"] = (start + timedelta(hours=7)).isoformat(sep=" ")
        self.write_report([current], "current.csv")

        MonitoringService().run(self.session)

        transaction = self.session.query(Transaction).filter_by(ext_txn_id="current").one()
        enrichment = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=transaction.id
        ).one()
        self.assertTrue(enrichment.history_sufficient)
        self.assertEqual(enrichment.enrichment_status, "AVAILABLE")

    def test_new_customer_retains_cold_start_behavior(self):
        self.write_report([self.row("new-customer", amount="75")], "new-customer.csv")
        transaction = self.session.query(Transaction).one()
        transaction.customer_id = "brand-new-customer"
        transaction.card_number = "brand-new-card"
        self.session.commit()

        MonitoringService().run(self.session)

        enrichment = self.session.query(TransactionAIEnrichment).one()
        self.assertFalse(enrichment.history_sufficient)
        self.assertEqual(enrichment.enrichment_status, "INSUFFICIENT_HISTORY")
        self.assertIsNone(enrichment.anomaly_score)
        self.assertIsNone(enrichment.anomaly_flag)


if __name__ == "__main__":
    unittest.main()
