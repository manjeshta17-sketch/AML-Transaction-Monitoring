"""Versioned transaction-level ML enrichment.

This service scores transactions with a pre-built Isolation Forest artifact.
It never trains during monitoring and never creates or changes AML alerts.
"""

from __future__ import annotations

import json
import math
import pickle
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.transaction import Transaction


MODEL_VERSION = "phase-4.2-isolation-forest-v1"
FEATURE_PIPELINE_VERSION = "behavioral-features-v1"
MIN_HISTORY = 5
VELOCITY_WINDOW_HOURS = 24
FEATURE_NAMES = (
    "amount",
    "log_amount",
    "customer_count",
    "card_count",
    "customer_total_amount",
    "card_total_amount",
    "customer_mean_amount",
    "card_mean_amount",
    "customer_amount_deviation",
    "card_amount_deviation",
    "customer_type_count",
    "customer_velocity_24h",
    "card_velocity_24h",
)
ARTIFACT_DIRECTORY = Path(__file__).resolve().parent / "artifacts"
MODEL_ARTIFACT_PATH = ARTIFACT_DIRECTORY / f"{MODEL_VERSION}.pkl"
MODEL_METADATA_PATH = ARTIFACT_DIRECTORY / f"{MODEL_VERSION}.json"


class MLModelUnavailable(RuntimeError):
    """Raised when the configured immutable model artifact cannot be used."""


@dataclass(frozen=True)
class EnrichmentResult:
    transaction_id: int
    model_version: str
    feature_pipeline_version: str
    anomaly_score: float | None
    anomaly_flag: bool | None
    history_sufficient: bool
    enrichment_status: str
    evidence_json: str


def historical_features(
    transactions: list[Transaction],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Build the exact prior-observation features used by the Phase 4.2 POC."""
    ordered = sorted(
        transactions,
        key=lambda item: (item.txn_date is None, item.txn_date, item.id),
    )
    customer_state: dict[str, list[float]] = defaultdict(list)
    card_state: dict[str, list[float]] = defaultdict(list)
    customer_type_counts: dict[str, Counter[str]] = defaultdict(Counter)
    customer_times: dict[str, deque[pd.Timestamp]] = defaultdict(deque)
    card_times: dict[str, deque[pd.Timestamp]] = defaultdict(deque)
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for transaction in ordered:
        customer = transaction.customer_id
        card = transaction.card_number
        amount = float(transaction.amount) if transaction.amount is not None else math.nan
        timestamp = pd.Timestamp(transaction.txn_date) if transaction.txn_date else None
        customer_amounts = customer_state.get(customer, []) if customer else []
        card_amounts = card_state.get(card, []) if card else []
        customer_count = len(customer_amounts)
        card_count = len(card_amounts)
        enough_history = (
            customer is not None
            and card is not None
            and customer_count >= MIN_HISTORY
            and card_count >= MIN_HISTORY
            and timestamp is not None
            and not math.isnan(amount)
        )
        customer_mean = float(np.mean(customer_amounts)) if customer_amounts else 0.0
        card_mean = float(np.mean(card_amounts)) if card_amounts else 0.0
        customer_velocity = 0
        card_velocity = 0
        if timestamp is not None and customer:
            while (
                customer_times[customer]
                and timestamp - customer_times[customer][0]
                > pd.Timedelta(hours=VELOCITY_WINDOW_HOURS)
            ):
                customer_times[customer].popleft()
            customer_velocity = len(customer_times[customer])
        if timestamp is not None and card:
            while (
                card_times[card]
                and timestamp - card_times[card][0]
                > pd.Timedelta(hours=VELOCITY_WINDOW_HOURS)
            ):
                card_times[card].popleft()
            card_velocity = len(card_times[card])

        rows.append(
            {
                "transaction_id": transaction.id,
                "amount": 0.0 if math.isnan(amount) else amount,
                "log_amount": math.log1p(max(amount, 0.0)) if not math.isnan(amount) else 0.0,
                "customer_count": customer_count,
                "card_count": card_count,
                "customer_total_amount": float(sum(customer_amounts)),
                "card_total_amount": float(sum(card_amounts)),
                "customer_mean_amount": customer_mean,
                "card_mean_amount": card_mean,
                "customer_amount_deviation": amount - customer_mean if customer_mean else 0.0,
                "card_amount_deviation": amount - card_mean if card_mean else 0.0,
                "customer_type_count": (
                    customer_type_counts[customer].get(transaction.transaction_type, 0)
                    if customer
                    else 0
                ),
                "customer_velocity_24h": customer_velocity,
                "card_velocity_24h": card_velocity,
            }
        )
        evidence.append(
            {
                "transaction_id": transaction.id,
                "customer_id": customer,
                "card_number": card,
                "transaction_type": transaction.transaction_type,
                "status": transaction.status,
                "amount": transaction.amount,
                "txn_date": transaction.txn_date,
                "history_sufficient": enough_history,
                "customer_history_count": customer_count,
                "card_history_count": card_count,
                "customer_mean_amount": customer_mean,
                "card_mean_amount": card_mean,
                "customer_amount_deviation": (
                    amount - customer_mean if customer_mean and not math.isnan(amount) else None
                ),
                "card_amount_deviation": (
                    amount - card_mean if card_mean and not math.isnan(amount) else None
                ),
                "customer_type_count": (
                    customer_type_counts[customer].get(transaction.transaction_type, 0)
                    if customer
                    else 0
                ),
                "customer_velocity_24h": customer_velocity,
                "card_velocity_24h": card_velocity,
            }
        )
        if customer and not math.isnan(amount):
            customer_state[customer].append(amount)
            customer_type_counts[customer][transaction.transaction_type] += 1
        if card and not math.isnan(amount):
            card_state[card].append(amount)
        if timestamp is not None and customer:
            customer_times[customer].append(timestamp)
        if timestamp is not None and card:
            card_times[card].append(timestamp)
    return pd.DataFrame(rows), evidence


def load_model_artifact() -> Any:
    if not MODEL_ARTIFACT_PATH.is_file() or not MODEL_METADATA_PATH.is_file():
        raise MLModelUnavailable("Configured ML model artifact is unavailable.")
    try:
        metadata = json.loads(MODEL_METADATA_PATH.read_text(encoding="utf-8"))
        if (
            metadata.get("model_version") != MODEL_VERSION
            or metadata.get("feature_pipeline_version") != FEATURE_PIPELINE_VERSION
            or tuple(metadata.get("feature_names", ())) != FEATURE_NAMES
        ):
            raise MLModelUnavailable("Configured ML model artifact metadata is incompatible.")
        with MODEL_ARTIFACT_PATH.open("rb") as artifact:
            return pickle.load(artifact)
    except (OSError, pickle.PickleError, ValueError, TypeError) as error:
        raise MLModelUnavailable("Configured ML model artifact could not be loaded.") from error


def _result(
    transaction_id: int,
    evidence: dict[str, Any],
    score: float | None,
    flag: bool | None,
    status: str,
) -> EnrichmentResult:
    return EnrichmentResult(
        transaction_id=transaction_id,
        model_version=MODEL_VERSION,
        feature_pipeline_version=FEATURE_PIPELINE_VERSION,
        anomaly_score=score,
        anomaly_flag=flag,
        history_sufficient=bool(evidence["history_sufficient"]),
        enrichment_status=status,
        evidence_json=json.dumps(evidence, sort_keys=True, default=str),
    )


def score_transactions(transactions: list[Transaction]) -> list[EnrichmentResult]:
    features, evidence = historical_features(transactions)
    evidence_by_id = {item["transaction_id"]: item for item in evidence}
    eligible = features.loc[
        features["customer_count"].ge(MIN_HISTORY)
        & features["card_count"].ge(MIN_HISTORY)
    ].copy()
    model = load_model_artifact()
    scores: dict[int, tuple[float, bool]] = {}
    if not eligible.empty:
        values = eligible.loc[:, FEATURE_NAMES].replace([np.inf, -np.inf], np.nan).dropna()
        if not values.empty:
            raw_scores = -model.decision_function(values)
            flags = model.predict(values) == -1
            scores = {
                int(transaction_id): (float(score), bool(flag))
                for transaction_id, score, flag in zip(
                    eligible.loc[values.index, "transaction_id"], raw_scores, flags
                )
            }
    results = []
    for transaction in transactions:
        item = evidence_by_id[transaction.id]
        if not item["history_sufficient"]:
            results.append(_result(transaction.id, item, None, None, "INSUFFICIENT_HISTORY"))
            continue
        score, flag = scores.get(transaction.id, (None, None))
        if score is None:
            results.append(_result(transaction.id, item, None, None, "ERROR"))
        else:
            results.append(_result(transaction.id, item, score, flag, "AVAILABLE"))
    return results


def unavailable_results(transactions: list[Transaction]) -> list[EnrichmentResult]:
    _, evidence = historical_features(transactions)
    return [
        _result(
            transaction.id,
            next(item for item in evidence if item["transaction_id"] == transaction.id),
            None,
            None,
            "INSUFFICIENT_HISTORY"
            if not next(item for item in evidence if item["transaction_id"] == transaction.id)[
                "history_sufficient"
            ]
            else "UNAVAILABLE",
        )
        for transaction in transactions
    ]


def persist_results(db: Session, results: list[EnrichmentResult]) -> None:
    for result in results:
        enrichment = (
            db.query(TransactionAIEnrichment)
            .filter(TransactionAIEnrichment.transaction_id == result.transaction_id)
            .one_or_none()
        )
        if enrichment is None:
            enrichment = TransactionAIEnrichment(transaction_id=result.transaction_id)
            db.add(enrichment)
        enrichment.model_version = result.model_version
        enrichment.feature_pipeline_version = result.feature_pipeline_version
        enrichment.anomaly_score = result.anomaly_score
        enrichment.anomaly_flag = result.anomaly_flag
        enrichment.history_sufficient = result.history_sufficient
        enrichment.enrichment_status = result.enrichment_status
        enrichment.evidence_json = result.evidence_json
        enrichment.generated_at = datetime.now(timezone.utc)
    db.commit()


def enrich_transactions(db: Session, transactions: list[Transaction]) -> None:
    if not transactions:
        return
    try:
        results = score_transactions(transactions)
    except MLModelUnavailable:
        results = unavailable_results(transactions)
    persist_results(db, results)
