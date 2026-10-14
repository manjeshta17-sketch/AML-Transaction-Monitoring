"""Grounded, optional LLM assistance for existing AML alerts."""

from __future__ import annotations

import importlib.util
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any, Protocol

from sqlalchemy.orm import Session

from backend.app.models.alert import Alert
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.llm_assistance import AlertLLMAssistance
from backend.app.models.transaction import Transaction
from backend.app.services.rule_configuration_service import RuleConfigurationService


PROMPT_VERSION = "phase-4.7-grounded-assistance-v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_HISTORY = 10
MAX_RESPONSE_LENGTH = 12000
SECTION_HEADERS = (
    "Alert Summary",
    "Evidence",
    "Missing Information",
    "Recommended Analyst Checks",
)
FORBIDDEN_DECISION_PATTERNS = (
    r"\bthis (transaction|alert|case) is fraudulent\b",
    r"\bthis is money laundering\b",
    r"\b(close|suppress|reject) the (alert|case|transaction)\b",
    r"\b(reject|close|suppress) (this )?(alert|case|transaction)\b",
    r"\b(final|definitive) (aml|fraud) decision\b",
)

SYSTEM_INSTRUCTION = """You are an AML investigation assistant.
Use only the structured evidence supplied by the user. Do not invent facts,
missing fields, geography, currency, history, or outcomes. Distinguish facts
from cautious interpretation and explicitly state relevant missing information.
Deterministic rule results are authoritative and must not be overridden,
suppressed, closed, rejected, or changed. An ML anomaly score is not a fraud
probability. An ML anomaly flag means unusual behavior according to the model,
not confirmed illicit activity. Do not decide that fraud or money laundering
occurred and do not claim an alert is legitimate or fraudulent from this
evidence alone. The analyst remains responsible for the final decision.
Return exactly these four headings in this order:
Alert Summary
Evidence
Missing Information
Recommended Analyst Checks
Recommend investigation checks and questions only."""


class LLMProvider(Protocol):
    provider_name: str
    model_name: str | None

    def complete(self, system_instruction: str, user_prompt: str) -> "ProviderResult":
        ...


@dataclass(frozen=True)
class ProviderResult:
    status: str
    text: str | None = None
    error: str | None = None


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, model: str | None = None):
        self.model_name = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    def complete(self, system_instruction: str, user_prompt: str) -> ProviderResult:
        if not os.getenv("OPENAI_API_KEY"):
            return ProviderResult("CREDENTIALS_UNAVAILABLE", error="Provider credentials are unavailable.")
        if importlib.util.find_spec("openai") is None:
            return ProviderResult("PROVIDER_UNAVAILABLE", error="Configured provider SDK is unavailable.")
        try:
            from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

            response = OpenAI().chat.completions.create(
                model=self.model_name,
                temperature=0,
                timeout=30,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                return ProviderResult("ERROR", error="Provider returned empty content.")
            return ProviderResult("SUCCESS", text=content)
        except (APITimeoutError, TimeoutError):
            return ProviderResult("TIMEOUT", error="Provider request timed out.")
        except (APIConnectionError, APIError, OSError, TypeError, ValueError):
            return ProviderResult("ERROR", error="Provider request failed.")


def mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_evidence(alert: Alert, transaction: Transaction, enrichment: TransactionAIEnrichment | None,
                   db: Session) -> dict[str, Any]:
    rules = RuleConfigurationService.load_rules(db)
    rule = next((item for item in rules if item.rule_code == alert.rule_code), None)
    history: dict[str, Any] = {}
    missing = [
        "No confirmed fraud or AML outcome is available.",
        "No investigation disposition is available.",
        "Long-term six- or twelve-month history is unavailable.",
    ]
    if enrichment and enrichment.evidence_json:
        try:
            enrichment_evidence = json.loads(enrichment.evidence_json)
            history = {
                key: enrichment_evidence.get(key)
                for key in (
                    "customer_history_count",
                    "card_history_count",
                    "customer_mean_amount",
                    "card_mean_amount",
                    "customer_amount_deviation",
                    "card_amount_deviation",
                    "customer_type_count",
                    "customer_velocity_24h",
                    "card_velocity_24h",
                )
                if key in enrichment_evidence
            }
        except (TypeError, ValueError):
            missing.append("Stored ML evidence could not be read.")

    related = (
        db.query(Transaction)
        .filter(Transaction.id != transaction.id)
        .filter(
            (Transaction.customer_id == transaction.customer_id)
            | (Transaction.card_number == transaction.card_number)
        )
        .order_by(Transaction.txn_date.desc(), Transaction.id.desc())
        .limit(MAX_HISTORY)
        .all()
    )
    bounded_history = [
        {
            "transaction_id": item.id,
            "transaction_type": item.transaction_type,
            "amount": item.amount,
            "currency": item.currency,
            "timestamp": _json_value(item.txn_date),
            "status": item.status,
        }
        for item in related
    ]
    if not transaction.currency:
        missing.append("Transaction currency is unavailable.")
    if not bounded_history:
        missing.append("No bounded related transaction history is available.")

    evidence: dict[str, Any] = {
        "alert_id": alert.alert_code,
        "rule": {
            "code": alert.rule_code,
            "name": alert.rule_name,
            "parameters": dict(rule.parameters) if rule else None,
        },
        "transaction": {
            "transaction_id": transaction.id,
            "transaction_type": transaction.transaction_type,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "timestamp": _json_value(transaction.txn_date),
            "customer_identifier": mask_identifier(transaction.customer_id),
            "card_identifier": mask_identifier(transaction.card_number),
        },
        "historical_behavior": history,
        "bounded_related_history": bounded_history,
        "ml_evidence": {
            "status": enrichment.enrichment_status if enrichment else "UNAVAILABLE",
            "anomaly_score": enrichment.anomaly_score if enrichment else None,
            "anomaly_flag": enrichment.anomaly_flag if enrichment else None,
            "model_version": enrichment.model_version if enrichment else None,
            "history_sufficient": enrichment.history_sufficient if enrichment else False,
            "score_interpretation": "Anomaly score indicates unusual behavior, not fraud probability.",
        },
        "missing_information": missing,
    }
    return evidence


def build_prompt(evidence: dict[str, Any]) -> tuple[str, str]:
    user_prompt = (
        "Prepare analyst assistance from this JSON evidence only. Use exactly "
        "the four required headings in the system instruction. Put concrete "
        "facts under Evidence and limitations under Missing Information. "
        "Do not add a final decision.\n\n"
        + json.dumps(evidence, indent=2, sort_keys=True, default=_json_value)
    )
    return SYSTEM_INSTRUCTION, user_prompt


def validate_response(text: str | None) -> list[str]:
    if not text or not text.strip():
        return ["Provider response is empty."]
    if len(text) > MAX_RESPONSE_LENGTH:
        return ["Provider response exceeds the allowed length."]
    positions = [text.find(f"## {header}") for header in SECTION_HEADERS]
    if any(position < 0 for position in positions):
        return ["Response is missing one or more required sections."]
    if positions != sorted(positions):
        return ["Required sections are not in the prescribed order."]
    for start, end in zip(positions, positions[1:] + [len(text)]):
        if not text[start + 3:end].strip():
            return ["A required response section is empty."]
    for pattern in FORBIDDEN_DECISION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return ["Response contains unsupported final-decision language."]
    return []


def generate_assistance(alert: Alert, transaction: Transaction,
                        enrichment: TransactionAIEnrichment | None, db: Session,
                        provider: LLMProvider | None = None) -> AlertLLMAssistance:
    evidence = build_evidence(alert, transaction, enrichment, db)
    system_instruction, user_prompt = build_prompt(evidence)
    configured_provider = provider or OpenAIProvider()
    started = monotonic()
    result = configured_provider.complete(system_instruction, user_prompt)
    latency_ms = int((monotonic() - started) * 1000)
    validated = result.status == "SUCCESS" and not validate_response(result.text)
    status = "VALID" if validated else (
        "INVALID" if result.status == "SUCCESS" else result.status
    )
    record = AlertLLMAssistance(
        alert_id=alert.id,
        provider=configured_provider.provider_name,
        model=configured_provider.model_name,
        prompt_version=PROMPT_VERSION,
        response_status=status,
        validated=validated,
        generated_response=result.text if validated else None,
        latency_ms=latency_ms,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
