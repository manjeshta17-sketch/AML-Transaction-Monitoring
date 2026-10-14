import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.transactions import get_transaction, list_transactions
from backend.app.core.database import Base
from backend.app.models.transaction import Transaction


class TransactionApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        for index, transaction_type in enumerate(("LOAD", "POS", "ATM", "POS", "LOAD")):
            self.session.add(Transaction(
                txn_date=datetime(2025, 5, 10 + index),
                corporate_name=f"merchant-{index % 2}",
                card_number=f"card-{index}",
                rrn=f"rrn-{index}",
                auth_code=f"auth-{index}",
                ext_txn_id=f"external-{index}",
                amount=100.0 + index * 100,
                transaction_type=transaction_type,
                status="PAYMENT_SUCCESS" if index < 4 else "REVERSED",
                customer_id=f"customer-{index % 2}",
                currency="036",
            ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_listing_pagination_filters_search_and_sorting(self):
        page = list_transactions(page=1, page_size=2, db=self.session)
        self.assertEqual(page.total, 5)
        self.assertEqual(page.total_pages, 3)
        self.assertEqual(len(page.transactions), 2)

        self.assertEqual(list_transactions(transaction_type="POS", db=self.session).total, 2)
        self.assertEqual(list_transactions(status="REVERSED", db=self.session).total, 1)
        self.assertEqual(list_transactions(customer_id="customer-1", db=self.session).total, 2)
        self.assertEqual(list_transactions(card_number="card-1", db=self.session).total, 1)
        self.assertEqual(list_transactions(corporate_name="merchant-0", db=self.session).total, 3)
        self.assertEqual(list_transactions(currency="036", db=self.session).total, 5)
        self.assertEqual(list_transactions(search="external-2", db=self.session).total, 1)
        self.assertEqual(list_transactions(search="rrn-3", db=self.session).total, 1)
        self.assertEqual(list_transactions(search="customer-0", db=self.session).total, 3)
        self.assertEqual(list_transactions(date_from=datetime(2025, 5, 12), db=self.session).total, 3)
        self.assertEqual(list_transactions(date_to=datetime(2025, 5, 12), db=self.session).total, 3)
        self.assertEqual(list_transactions(amount_min=300, amount_max=400, db=self.session).total, 2)
        descending = list_transactions(sort_by="amount", sort_order="desc", db=self.session)
        self.assertEqual(descending.transactions[0].amount, 500)

    def test_invalid_filters_and_detail(self):
        for kwargs in (
            {"page": 0},
            {"page_size": 101},
            {"sort_by": "unsafe"},
            {"sort_order": "sideways"},
            {"date_from": datetime(2025, 6, 1), "date_to": datetime(2025, 5, 1)},
            {"amount_min": 500, "amount_max": 100},
            {"amount_min": -1},
        ):
            with self.assertRaises(HTTPException):
                list_transactions(db=self.session, **kwargs)

        detail = get_transaction(1, db=self.session)
        self.assertEqual(detail.ext_txn_id, "external-0")
        self.assertEqual(detail.transaction_type, "LOAD")
        self.assertEqual(detail.alert_count, 0)
        with self.assertRaises(HTTPException) as error:
            get_transaction(999, db=self.session)
        self.assertEqual(error.exception.status_code, 404)

    def test_nullable_fields_are_returned_as_null(self):
        transaction = self.session.get(Transaction, 1)
        self.assertIsNone(get_transaction(transaction.id, db=self.session).description)
