"""Generate the isolated Phase 4.3 analyst-facing ML evaluation report."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.rule_engine import RuleEngine
from scripts.phase_4_2_ml_poc import (
    DEFAULT_DATASET,
    DEFAULT_OUTPUT,
    historical_features,
    load_transactions,
)

REPORT = PROJECT_ROOT / "docs" / "PHASE_4_3_ML_EVALUATION_REPORT.md"
EXAMPLES = PROJECT_ROOT / "docs" / "PHASE_4_3_SELECTED_EXAMPLES.csv"


def mask(value: object, visible: int = 4) -> str:
    text = "" if value is None else str(value)
    if len(text) <= visible:
        return text
    return f"{text[:visible]}...{text[-visible:]}"


def rule_context(transactions: list[object]) -> dict[int, list[str]]:
    outcome = RuleEngine().evaluate_with_context(transactions)
    result: dict[int, list[str]] = {}
    for trigger in outcome.triggers:
        if trigger.transaction_id is not None:
            result.setdefault(trigger.transaction_id, []).append(trigger.rule_code)
    return result


def explanation(row: pd.Series) -> str:
    amount = float(row["amount"])
    customer_mean = float(row["customer_mean_amount"])
    card_mean = float(row["card_mean_amount"])
    parts: list[str] = []
    if customer_mean > 0 and amount > customer_mean * 2:
        parts.append(
            f"amount {amount:.2f} was more than twice the customer historical average "
            f"({customer_mean:.2f})"
        )
    elif customer_mean > 0 and amount < customer_mean * 0.25:
        parts.append(
            f"amount {amount:.2f} was materially below the customer historical average "
            f"({customer_mean:.2f})"
        )
    if card_mean > 0 and amount > card_mean * 2:
        parts.append(
            f"amount was more than twice the card historical average ({card_mean:.2f})"
        )
    elif card_mean > 0 and amount < card_mean * 0.25:
        parts.append(
            f"amount was materially below the card historical average ({card_mean:.2f})"
        )
    if int(row["customer_velocity_24h"]) >= 3 or int(row["card_velocity_24h"]) >= 3:
        parts.append(
            "the preceding 24-hour window already contained "
            f"{int(row['customer_velocity_24h'])}/{int(row['card_velocity_24h'])} "
            "customer/card transactions"
        )
    if not parts:
        parts.append(
            f"amount {amount:.2f} differed from the customer/card historical averages "
            f"({customer_mean:.2f}/{card_mean:.2f}); prior history was "
            f"{int(row['customer_history_count'])}/{int(row['card_history_count'])} "
            f"transactions and 24-hour velocity was "
            f"{int(row['customer_velocity_24h'])}/{int(row['card_velocity_24h'])}"
        )
    return "Transaction " + "; ".join(parts) + "."


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "No rows."
    rows = frame[columns].fillna("").astype(str).values.tolist()
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    frame, transactions = load_transactions(DEFAULT_DATASET)
    features, evidence = historical_features(transactions)
    scores = pd.read_csv(DEFAULT_OUTPUT)
    evidence_frame = pd.DataFrame(evidence)
    merged = evidence_frame.merge(
        features[["transaction_id", "customer_type_count"]],
        on="transaction_id",
        how="left",
    ).merge(
        scores[["transaction_id", "anomaly_score", "anomaly_flag"]],
        on="transaction_id",
        how="left",
    )
    merged["anomaly_flag"] = merged["anomaly_flag"].fillna(False).astype(bool)
    merged["anomaly_score"] = pd.to_numeric(merged["anomaly_score"], errors="coerce")
    rules = rule_context(transactions)
    merged["rule_codes"] = merged["transaction_id"].map(
        lambda value: ", ".join(rules.get(int(value), []))
    )
    merged["has_rule_trigger"] = merged["rule_codes"].ne("")
    eligible = merged[merged["anomaly_score"].notna()].copy()
    flagged = eligible[eligible["anomaly_flag"]]
    ml_only = flagged[~flagged["has_rule_trigger"]]
    overlap = flagged[flagged["has_rule_trigger"]]
    rule_only = eligible[eligible["has_rule_trigger"] & ~eligible["anomaly_flag"]]
    normal = eligible[~eligible["has_rule_trigger"] & ~eligible["anomaly_flag"]]

    # Selection is deterministic: highest score in each requested cohort, with
    # transaction ID as a stable tie-breaker. The normal comparator is closest
    # to the median eligible score among non-anomalous, non-rule rows.
    normal_median = float(normal["anomaly_score"].median())
    candidates = {
        "ML anomaly + existing rule trigger": overlap.sort_values(
            ["anomaly_score", "transaction_id"], ascending=[False, True]
        ).head(1),
        "ML anomaly + no existing rule trigger": ml_only.sort_values(
            ["anomaly_score", "transaction_id"], ascending=[False, True]
        ).head(1),
        "Existing rule trigger + no ML anomaly": rule_only.sort_values(
            ["anomaly_score", "transaction_id"], ascending=[False, True]
        ).head(1),
        "Normal/non-anomalous comparison": normal.assign(
            median_distance=(normal["anomaly_score"] - normal_median).abs()
        ).sort_values(["median_distance", "transaction_id"]).head(1),
    }
    selected_rows: list[dict[str, object]] = []
    for cohort, selected in candidates.items():
        if selected.empty:
            continue
        row = selected.iloc[0]
        selected_rows.append({
            "cohort": cohort,
            "transaction_id": int(row["transaction_id"]),
            "customer_id": mask(row["customer_id"]),
            "card_number": mask(row["card_number"]),
            "txn_date": row["txn_date"],
            "transaction_type": row["transaction_type"],
            "amount": float(row["amount"]),
            "anomaly_score": float(row["anomaly_score"]),
            "anomaly_flag": bool(row["anomaly_flag"]),
            "customer_history_count": int(row["customer_history_count"]),
            "card_history_count": int(row["card_history_count"]),
            "customer_historical_average": float(row["customer_mean_amount"]),
            "card_historical_average": float(row["card_mean_amount"]),
            "customer_amount_deviation": float(row["amount"] - row["customer_mean_amount"]),
            "card_amount_deviation": float(row["amount"] - row["card_mean_amount"]),
            "customer_velocity_24h": int(row["customer_velocity_24h"]),
            "card_velocity_24h": int(row["card_velocity_24h"]),
            "customer_type_count": int(row["customer_type_count"]),
            "rule_codes": row["rule_codes"] or "None",
            "explanation": explanation(row),
        })
    selected_frame = pd.DataFrame(selected_rows)
    EXAMPLES.parent.mkdir(parents=True, exist_ok=True)
    selected_frame.to_csv(EXAMPLES, index=False)

    type_summary = (
        ml_only.groupby("transaction_type")
        .agg(count=("transaction_id", "size"), min_amount=("amount", "min"), max_amount=("amount", "max"))
        .sort_values("count", ascending=False)
        .reset_index()
    )
    customer_repeats = int(ml_only["customer_id"].value_counts().gt(1).sum())
    card_repeats = int(ml_only["card_number"].value_counts().gt(1).sum())
    rule_summary = Counter(code for codes in rule_only["rule_codes"] for code in codes.split(", "))

    selected_display = selected_frame.copy()
    selected_display["amount"] = selected_display["amount"].map(lambda value: f"{value:.2f}")
    selected_display["anomaly_score"] = selected_display["anomaly_score"].map(lambda value: f"{value:.4f}")
    selected_display["customer_historical_average"] = selected_display["customer_historical_average"].map(lambda value: f"{value:.2f}")
    selected_display["card_historical_average"] = selected_display["card_historical_average"].map(lambda value: f"{value:.2f}")
    selected_display["customer_amount_deviation"] = selected_display["customer_amount_deviation"].map(lambda value: f"{value:.2f}")
    selected_display["card_amount_deviation"] = selected_display["card_amount_deviation"].map(lambda value: f"{value:.2f}")
    selected_display["explanation"] = selected_display["explanation"].str.replace("|", "\\|", regex=False)

    report = f"""# Phase 4.3 — AI/ML Evaluation and Explainable Alert Enrichment POC

## 1. Scope and evaluation method

This isolated evaluation uses the Phase 4.2 Isolation Forest scores and reuses
the Phase 4.2 historical feature-generation pipeline. It does not train a new
model, modify the application, persist alerts, or call FastAPI. Existing rule
context was derived by running the current rule engine in memory against the
same transaction objects.

The Phase 4.2 score direction is retained: higher `anomaly_score` means more
unusual relative to observed prior behavior. It is not a fraud probability.

Representative selection was deterministic, not random:

1. For each requested cohort, select the highest anomaly score.
2. Break ties using the lowest transaction ID.
3. For the normal comparator, select the non-anomalous/non-rule transaction
   closest to the median eligible anomaly score, then use the lowest ID.

## 2. Population evaluated

| Population | Count |
|---|---:|
| Transactions in supplied extract | {len(frame):,} |
| ML-eligible transactions with scores | {len(eligible):,} |
| ML-flagged transactions | {len(flagged):,} |
| ML anomaly + existing rule trigger | {len(overlap):,} |
| ML anomaly + no existing rule trigger | {len(ml_only):,} |
| Existing rule trigger + no ML anomaly | {len(rule_only):,} |
| Normal/non-anomalous comparison population | {len(normal):,} |

The extract covers six days and has no confirmed fraud, AML, investigation, or
case-outcome labels. Rule triggers were used only as context, never as labels.

## 3. Representative transactions and generated evidence

Customer and card identifiers are masked in this report and the compact CSV.
All other values below are taken from the supplied transaction data and the
computed historical features.

{markdown_table(selected_display, [
    "cohort", "transaction_id", "customer_id", "card_number", "txn_date",
    "transaction_type", "amount", "anomaly_score", "anomaly_flag",
    "customer_history_count", "card_history_count",
    "customer_historical_average", "card_historical_average",
    "customer_amount_deviation", "card_amount_deviation",
    "customer_velocity_24h", "card_velocity_24h", "customer_type_count",
    "rule_codes", "explanation"
])}

The explanations are deterministic templates based on actual amount baselines
and velocity values. No LLM or causal inference was used. “Unusual” describes
the model-relative behavior only; it does not mean illicit activity.

## 4. ML-only analysis

The {len(ml_only):,} ML-only flags are distributed as follows:

{markdown_table(type_summary, ["transaction_type", "count", "min_amount", "max_amount"]) if not type_summary.empty else "No ML-only rows."}

ML-only amount range: **{ml_only["amount"].min():.2f} to {ml_only["amount"].max():.2f}**
when rows are present. The number of customers with more than one ML-only flag
is **{customer_repeats}**, and the number of cards with more than one ML-only
flag is **{card_repeats}**.

The concentration is therefore primarily transaction-type-specific, especially
where the observed amount and historical behavior combination is unusual. The
results provide potentially useful additional monitoring signals, but they do
not establish missed fraud or missed AML cases. The model has no labels or
causal evidence with which to make that claim.

## 5. Rule-only analysis

The {len(rule_only):,} rule-only eligible rows demonstrate why deterministic
rules must remain authoritative. Rule-only rows were generated by configured
conditions such as explicit thresholds or repeated merchant activity, while
the behavioral model did not flag them as multivariate outliers. Rule-only
context by code:

{markdown_table(pd.DataFrame([{"rule_code": code, "rule_only_rows": count} for code, count in sorted(rule_summary.items())]), ["rule_code", "rule_only_rows"])}

The selected rule-only example is evidence of a deterministic rule signal that
should not be replaced merely because the ML score is normal. A normal ML
score means only that the transaction was not isolated by this model and
feature population.

## 6. Does ML add useful complementary information?

| Question | Evidence-based conclusion |
|---|---|
| Does ML add information beyond deterministic rules? | Yes, in this POC it produces {len(ml_only):,} eligible ML-only candidates, including behavior not selected by the configured rule triggers. This is complementary signal evidence, not case-outcome validation. |
| What does it capture? | Unusual combinations of amount, customer/card baseline deviation, prior activity volume, transaction-type history, and 24-hour velocity. |
| Where is it weak? | It is population-relative, sensitive to contamination and feature coverage, does not explain causality, and leaves cold-start rows unscored. |
| What data is missing? | The extract lacks populated country, home currency, domestic status, load source, settlement currency, and originating-country currency; it also lacks confirmed outcomes and longer history. |
| Is it useful for alert prioritization? | Potentially, as a review-order enrichment for analysts. This POC supports a candidate use case but does not measure operational uplift. |
| Should analysts see the score? | Yes, with score direction, history sufficiency, model version, and evidence features shown together; never as a fraud probability. |
| Should it affect final AML decisions? | No. It should not create, suppress, close, or override deterministic alerts or analyst decisions. |

## 7. Proposed conceptual alert enrichment object

This object is a design only and is not implemented:

```text
ai_enrichment:
  anomaly_score: number | null
  anomaly_flag: boolean | null
  history_sufficiency: "sufficient" | "insufficient"
  evidence_features:
    amount: number
    customer_historical_average: number | null
    card_historical_average: number | null
    customer_amount_deviation: number | null
    card_amount_deviation: number | null
    customer_history_count: integer
    card_history_count: integer
    customer_velocity_24h: integer | null
    card_velocity_24h: integer | null
  model_version: "phase-4.2-isolation-forest-v1"
  generated_at: timestamp
```

This could later be attached to an existing alert as enrichment while leaving
the original rule code, rule result, risk level, and alert lifecycle unchanged.
For cold-start rows, score and flag remain null rather than fabricated values.

## 8. Evaluation limitations

- No fraud or AML labels exist; no accuracy, precision, recall, F1, ROC-AUC,
  or other supervised metric was calculated.
- No analyst investigation outcomes or case dispositions exist.
- The source extract spans only six days.
- Cold-start and insufficient-history rows are excluded from scoring.
- Isolation Forest contamination is a modeling assumption, not fraud prevalence.
- An anomaly is not evidence of illicit activity.
- The feature explanation is descriptive, not causal.
- Rule triggers were not treated as ground truth.
- The supplied CSV is a development/evaluation extract, not a production
  baseline.
- This POC does not measure alert-prioritization uplift or analyst time saved.

## 9. Recommended next step

Keep the enrichment isolated until longer validated history and analyst review
outcomes are available. If later integrated, present the score and evidence
alongside existing rule alerts, preserve nulls for insufficient history, log
model version and generation time, and evaluate prioritization with defined
analyst outcome measures rather than claiming fraud accuracy.

## 10. Phase boundary confirmation

No FastAPI integration, API endpoint, database schema, alert/case behavior,
frontend, rule definition, alternative model, or LLM was implemented.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(f"Report written to {REPORT}")
    print(f"Examples written to {EXAMPLES}")
    print(f"ML-only rows: {len(ml_only)}")
    print(f"Rule-only rows: {len(rule_only)}")


if __name__ == "__main__":
    main()
