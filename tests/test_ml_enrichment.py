from datetime import datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.transactions import get_ai_enrichment
from backend.app.core.database import Base
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.services.ml_service import MODEL_ARTIFACT_PATH
from backend.app.services.monitoring_service import MonitoringService


class MLTransactionEnrichmentTests(unittest.TestCase):
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

    def add_history(self, current_type="POS", current_amount=50.0):
        start = datetime(2025, 5, 12)
        for index in range(6):
            self.session.add(
                Transaction(
                    ext_txn_id=f"history-{index}",
                    txn_date=start + timedelta(hours=index),
                    transaction_type="POS",
                    status="PAYMENT_SUCCESS",
                    amount=50.0 + index,
                    customer_id="customer-1",
                    card_number="4111XXXXXXXX1111",
                )
            )
        current = Transaction(
            ext_txn_id="current",
            txn_date=start + timedelta(hours=7),
            transaction_type=current_type,
            status="PAYMENT_SUCCESS",
            amount=current_amount,
            customer_id="customer-1",
            card_number="4111XXXXXXXX1111",
        )
        self.session.add(current)
        self.session.commit()
        return current

    def test_sufficient_history_gets_available_enrichment(self):
        current = self.add_history()

        MonitoringService().run(self.session)

        enrichment = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=current.id
        ).one()
        self.assertTrue(enrichment.history_sufficient)
        self.assertEqual(enrichment.enrichment_status, "AVAILABLE")
        self.assertIsNotNone(enrichment.anomaly_score)
        self.assertIsNotNone(enrichment.anomaly_flag)

    def test_insufficient_history_gets_null_score_and_flag(self):
        transaction = Transaction(
            ext_txn_id="cold-start",
            txn_date=datetime(2025, 5, 12),
            transaction_type="POS",
            status="PAYMENT_SUCCESS",
            amount=25.0,
            customer_id="new-customer",
            card_number="4111XXXXXXXX2222",
        )
        self.session.add(transaction)
        self.session.commit()

        MonitoringService().run(self.session)

        enrichment = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=transaction.id
        ).one()
        self.assertFalse(enrichment.history_sufficient)
        self.assertEqual(enrichment.enrichment_status, "INSUFFICIENT_HISTORY")
        self.assertIsNone(enrichment.anomaly_score)
        self.assertIsNone(enrichment.anomaly_flag)

    def test_missing_model_artifact_does_not_break_deterministic_monitoring(self):
        transaction = self.add_history(current_type="LOAD", current_amount=6000.0)

        with patch(
            "backend.app.services.ml_service.MODEL_ARTIFACT_PATH",
            Path("missing-model-artifact.pkl"),
        ):
            result = MonitoringService().run(self.session)

        self.assertEqual(result.alerts_generated, 1)
        self.assertEqual(result.alerts_by_rule, {"R001": 1})
        self.assertEqual(self.session.query(Alert).count(), 1)
        enrichment = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=transaction.id
        ).one()
        self.assertEqual(enrichment.enrichment_status, "UNAVAILABLE")
        self.assertIsNone(enrichment.anomaly_score)

    def test_ml_enrichment_does_not_create_or_change_rule_alert_ownership(self):
        transaction = self.add_history(current_type="LOAD", current_amount=6000.0)

        MonitoringService().run(self.session)

        alerts = self.session.query(Alert).all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule_code, "R001")
        self.assertEqual(alerts[0].transaction_id, transaction.id)
        self.assertEqual(self.session.query(TransactionAIEnrichment).count(), 7)

    def test_repeated_enrichment_is_deterministic_for_same_model_and_input(self):
        transaction = self.add_history()

        MonitoringService().run(self.session)
        first = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=transaction.id
        ).one()
        first_values = (first.model_version, first.anomaly_score, first.anomaly_flag)

        MonitoringService().run(self.session)
        second = self.session.query(TransactionAIEnrichment).filter_by(
            transaction_id=transaction.id
        ).one()
        self.assertEqual(
            first_values,
            (second.model_version, second.anomaly_score, second.anomaly_flag),
        )
        self.assertEqual(self.session.query(TransactionAIEnrichment).count(), 7)

    def test_enrichment_api_returns_persisted_enrichment(self):
        transaction = self.add_history()
        MonitoringService().run(self.session)

        response = get_ai_enrichment(transaction.id, db=self.session)

        self.assertEqual(response.transaction_id, transaction.id)
        self.assertEqual(response.enrichment_status, "AVAILABLE")
        self.assertEqual(response.feature_pipeline_version, "behavioral-features-v1")

    def test_enrichment_api_returns_not_found_for_missing_enrichment(self):
        transaction = Transaction(
            ext_txn_id="not-enriched",
            customer_id="customer-2",
            card_number="4111XXXXXXXX3333",
        )
        self.session.add(transaction)
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            get_ai_enrichment(transaction.id, db=self.session)

        self.assertEqual(context.exception.status_code, 404)
