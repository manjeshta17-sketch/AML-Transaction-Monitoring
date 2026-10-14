from datetime import datetime
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import generate_alert_ai_assistance
from backend.app.core.database import Base
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.services.llm_service import (
    PROMPT_VERSION,
    ProviderResult,
    build_evidence,
    build_prompt,
    generate_assistance,
    validate_response,
)


VALID_RESPONSE = """## Alert Summary
The transaction triggered the supplied deterministic rule.

## Evidence
- The supplied transaction and rule details are listed in the evidence.

## Missing Information
- No confirmed investigation outcome is available.

## Recommended Analyst Checks
- Review the bounded related transaction history and source-of-funds evidence.
"""


class MockProvider:
    provider_name = "mock"
    model_name = "deterministic-test-model"

    def __init__(self, result: ProviderResult):
        self.result = result

    def complete(self, system_instruction: str, user_prompt: str) -> ProviderResult:
        return self.result


class LLMAssistanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.transaction = Transaction(
            ext_txn_id="txn-1",
            txn_date=datetime(2025, 5, 12, 10, 0),
            transaction_type="POS",
            status="PAYMENT_SUCCESS",
            amount=125.0,
            currency="USD",
            customer_id="customer-abcdef",
            card_number="4111111111111111",
        )
        self.session.add(self.transaction)
        self.session.commit()
        self.alert = Alert(
            alert_code="ALT-R001-T00000001",
            rule_code="R001",
            rule_name="High-value card load",
            description="Rule R001 matched",
            transaction_id=self.transaction.id,
            customer_id=self.transaction.customer_id,
            card_number=self.transaction.card_number,
            amount=self.transaction.amount,
            risk_level="high",
            priority=1,
            status="OPEN",
        )
        self.session.add(self.alert)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def enrichment(self):
        enrichment = TransactionAIEnrichment(
            transaction_id=self.transaction.id,
            model_version="phase-4.2-isolation-forest-v1",
            feature_pipeline_version="behavioral-features-v1",
            anomaly_score=0.82,
            anomaly_flag=True,
            history_sufficient=True,
            enrichment_status="AVAILABLE",
            evidence_json=json.dumps({
                "customer_history_count": 6,
                "card_history_count": 6,
                "customer_mean_amount": 50.0,
                "card_mean_amount": 52.0,
                "customer_velocity_24h": 3,
                "card_velocity_24h": 3,
            }),
        )
        self.session.add(enrichment)
        self.session.commit()
        return enrichment

    def test_evidence_includes_verified_rule_and_ml_information(self):
        evidence = build_evidence(self.alert, self.transaction, self.enrichment(), self.session)
        self.assertEqual(evidence["rule"]["code"], "R001")
        self.assertIn("amount_threshold", evidence["rule"]["parameters"])
        self.assertEqual(evidence["ml_evidence"]["model_version"], "phase-4.2-isolation-forest-v1")
        self.assertTrue(evidence["ml_evidence"]["anomaly_flag"])
        self.assertTrue(evidence["transaction"]["card_identifier"].endswith("1111"))

    def test_evidence_reports_unavailable_information(self):
        evidence = build_evidence(self.alert, self.transaction, None, self.session)
        self.assertEqual(evidence["ml_evidence"]["status"], "UNAVAILABLE")
        self.assertIsNone(evidence["ml_evidence"]["anomaly_score"])
        self.assertTrue(evidence["missing_information"])

    def test_prompt_contains_no_raw_csv_or_filesystem_content(self):
        _, prompt = build_prompt(build_evidence(self.alert, self.transaction, None, self.session))
        self.assertNotIn(".csv", prompt)
        self.assertNotIn("OneDrive", prompt)
        self.assertNotIn("4111111111111111", prompt)

    def test_provider_unavailable_is_persisted_without_fabricated_response(self):
        record = generate_assistance(
            self.alert, self.transaction, None, self.session,
            MockProvider(ProviderResult("PROVIDER_UNAVAILABLE", error="unavailable")),
        )
        self.assertEqual(record.response_status, "PROVIDER_UNAVAILABLE")
        self.assertFalse(record.validated)
        self.assertIsNone(record.generated_response)

    def test_successful_response_is_validated_and_persisted(self):
        record = generate_assistance(
            self.alert, self.transaction, self.enrichment(), self.session,
            MockProvider(ProviderResult("SUCCESS", text=VALID_RESPONSE)),
        )
        self.assertEqual(record.response_status, "VALID")
        self.assertTrue(record.validated)
        self.assertEqual(record.prompt_version, PROMPT_VERSION)

    def test_malformed_response_is_not_trusted(self):
        record = generate_assistance(
            self.alert, self.transaction, None, self.session,
            MockProvider(ProviderResult("SUCCESS", text="not structured")),
        )
        self.assertEqual(record.response_status, "INVALID")
        self.assertFalse(record.validated)
        self.assertIsNone(record.generated_response)

    def test_missing_section_and_forbidden_language_are_rejected(self):
        self.assertTrue(validate_response("## Alert Summary\nOnly one section."))
        forbidden = VALID_RESPONSE.replace(
            "The transaction triggered the supplied deterministic rule.",
            "This transaction is fraudulent.",
        )
        self.assertTrue(validate_response(forbidden))

    def test_endpoint_does_not_modify_alert_workflow_or_create_alerts(self):
        original = (self.alert.status, self.alert.priority)
        response = generate_alert_ai_assistance(
            self.alert.id, self.session,
        )
        self.assertEqual(response.response_status, "CREDENTIALS_UNAVAILABLE")
        self.session.refresh(self.alert)
        self.assertEqual((self.alert.status, self.alert.priority), original)
        self.assertEqual(self.session.query(Alert).count(), 1)

    def test_missing_alert_returns_not_found(self):
        with self.assertRaises(HTTPException) as context:
            generate_alert_ai_assistance(999, self.session)
        self.assertEqual(context.exception.status_code, 404)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-only"}, clear=True)
    def test_provider_sdk_unavailable_is_explicit(self):
        record = generate_assistance(
            self.alert, self.transaction, None, self.session,
        )
        self.assertEqual(record.response_status, "PROVIDER_UNAVAILABLE")

