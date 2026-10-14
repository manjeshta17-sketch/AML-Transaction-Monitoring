import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.transaction import Transaction
from backend.app.services.transaction_service import REQUIRED_COLUMNS, import_transactions


class TransactionImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        file_descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        os.close(file_descriptor)
        self.csv_path = Path(file_path)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        self.csv_path.unlink(missing_ok=True)

    def write_report(self, header=REQUIRED_COLUMNS):
        row = ["" for _ in header]
        values = {
            "Txn Date": "2025-05-18 23:57:23.000000",
            "Ext Txn Id": "unique-transaction-1",
            "Amount": "72.82",
            "ActivationDate": "2025-02-11",
        }
        row = [values.get(column, "value") for column in header]
        self.csv_path.write_text(
            "Transaction Report\n05/19/2025\n"
            + "|".join(header)
            + "\n"
            + "|".join(row)
            + "\n",
            encoding="utf-8",
        )

    def test_imports_all_fields_and_skips_a_repeat_import(self):
        self.write_report()

        self.assertEqual(import_transactions(str(self.csv_path), self.session), 1)
        self.assertEqual(import_transactions(str(self.csv_path), self.session), 0)
        transaction = self.session.query(Transaction).one()
        self.assertEqual(transaction.ext_txn_id, "unique-transaction-1")
        self.assertEqual(transaction.amount, 72.82)

    def test_rejects_missing_required_columns(self):
        self.write_report(REQUIRED_COLUMNS[:-1])

        with self.assertRaisesRegex(ValueError, "ActivationDate"):
            import_transactions(str(self.csv_path), self.session)


if __name__ == "__main__":
    unittest.main()
