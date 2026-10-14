"""Reproducible Phase 4.2 anomaly-detection proof of concept.

This script reads the immutable pipe-delimited transaction report, builds
strictly historical behavioral features, scores eligible transactions with an
unsupervised Isolation Forest, and writes a Markdown report. It never writes
to aml.db and never changes rule or alert behavior.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import RuleEngine
from backend.app.services.ml_service import historical_features
from backend.app.services.transaction_service import (
    COLUMN_MAPPING,
    OPTIONAL_COLUMN_MAPPING,
    REQUIRED_COLUMNS,
)


DEFAULT_DATASET = Path("data/raw/OXYGPRPPAU_TransactionReport_2025-05-12_to_2025-05-18.csv")
DEFAULT_REPORT = Path("docs/PHASE_4_2_ML_POC_REPORT.md")
DEFAULT_OUTPUT = Path("docs/PHASE_4_2_ML_POC_SCORES.csv")
RANDOM_SEED = 42
N_ESTIMATORS = 200
CONTAMINATION = 0.02
MIN_HISTORY = 5
VELOCITY_WINDOW_HOURS = 24


def load_transactions(path: Path) -> tuple[pd.DataFrame, list[Transaction]]:
    frame = pd.read_csv(path, sep="|", skiprows=2, dtype=str)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    selected = list(REQUIRED_COLUMNS) + [
        column for column in OPTIONAL_COLUMN_MAPPING if column in frame.columns
    ]
    frame = frame.loc[:, selected].rename(
        columns={**COLUMN_MAPPING, **OPTIONAL_COLUMN_MAPPING}
    )
    for column in OPTIONAL_COLUMN_MAPPING.values():
        if column not in frame:
            frame[column] = None
    for column in ("amount", "post_wallet_balance", "txn_amount", "fees"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("txn_date", "activation_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame = frame.astype(object).where(pd.notna(frame), None)

    transactions: list[Transaction] = []
    for identifier, row in enumerate(frame.to_dict(orient="records"), start=1):
        transactions.append(Transaction(id=identifier, **row))
    return frame, transactions


def profile(frame: pd.DataFrame) -> dict[str, Any]:
    date_values = pd.to_datetime(frame["txn_date"], errors="coerce").dropna()
    amount = pd.to_numeric(frame["amount"], errors="coerce")
    missingness = {
        column: int(frame[column].isna().sum())
        for column in frame.columns
        if frame[column].isna().any()
    }
    return {
        "transactions": len(frame),
        "date_min": str(date_values.min()) if len(date_values) else "Unavailable",
        "date_max": str(date_values.max()) if len(date_values) else "Unavailable",
        "unique_customers": int(frame["customer_id"].nunique(dropna=True)),
        "unique_cards": int(frame["card_number"].nunique(dropna=True)),
        "transaction_types": frame["transaction_type"].fillna("<missing>").value_counts().to_dict(),
        "statuses": frame["status"].fillna("<missing>").value_counts().to_dict(),
        "amount_statistics": {
            "count": int(amount.notna().sum()),
            "min": float(amount.min()),
            "median": float(amount.median()),
            "mean": float(amount.mean()),
            "max": float(amount.max()),
        },
        "missingness": missingness,
        "optional_columns_present": [
            column for column in OPTIONAL_COLUMN_MAPPING if column in frame.columns and frame[column].notna().any()
        ],
        "history_days": int((date_values.max() - date_values.min()).days) if len(date_values) else 0,
    }


def rule_trigger_ids(transactions: list[Transaction]) -> set[int]:
    outcome = RuleEngine().evaluate_with_context(transactions)
    return {result.transaction_id for result in outcome.triggers if result.transaction_id is not None}


def md_table(rows: list[list[str]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def write_scores(output: Path, scored: pd.DataFrame, evidence: list[dict[str, Any]]) -> None:
    evidence_frame = pd.DataFrame(evidence).set_index("transaction_id")
    eligible = scored.loc[scored["history_sufficient"]].set_index("transaction_id")
    output_frame = evidence_frame.loc[eligible.index, [
        "customer_id", "card_number", "transaction_type", "status", "amount",
        "txn_date", "customer_history_count", "card_history_count",
        "customer_mean_amount", "card_mean_amount", "customer_velocity_24h",
        "card_velocity_24h",
    ]].copy()
    output_frame["history_sufficient"] = True
    output_frame["anomaly_score"] = eligible["anomaly_score"]
    output_frame["anomaly_flag"] = eligible["anomaly_flag"]
    output_frame.index.name = "transaction_id"
    output.parent.mkdir(parents=True, exist_ok=True)
    output_frame.reset_index().to_csv(output, index=False)


def build_report(
    dataset: Path,
    report: Path,
    data_profile: dict[str, Any],
    scored: pd.DataFrame,
    evidence: list[dict[str, Any]],
    rule_ids: set[int],
) -> None:
    evidence_by_id = {item["transaction_id"]: item for item in evidence}
    eligible = scored[scored["history_sufficient"]]
    flagged = eligible[eligible["anomaly_flag"]]
    eligible_ids = set(eligible.transaction_id)
    flagged_ids = set(flagged.transaction_id)
    comparable_rule_ids = eligible_ids & rule_ids
    both = len(flagged_ids & comparable_rule_ids)
    rule_only = len(comparable_rule_ids - flagged_ids)
    ml_only = len(flagged_ids - comparable_rule_ids)
    neither = len(eligible_ids - flagged_ids - comparable_rule_ids)
    top = eligible.sort_values("anomaly_score", ascending=False).head(5)
    examples = []
    for row in top.itertuples():
        item = evidence_by_id[row.transaction_id]
        examples.append([
            str(row.transaction_id),
            str(item["transaction_type"]),
            f"{float(item['amount']):.2f}",
            f"{row.anomaly_score:.4f}",
            "Yes" if row.anomaly_flag else "No",
            "Yes" if row.transaction_id in rule_ids else "No",
            f"customer history={item['customer_history_count']}, card history={item['card_history_count']}, "
            f"24h velocity={item['customer_velocity_24h']}/{item['card_velocity_24h']}",
        ])
    feature_names = [
        "amount", "log_amount", "customer_count", "card_count",
        "customer_total_amount", "card_total_amount", "customer_mean_amount",
        "card_mean_amount", "customer_amount_deviation", "card_amount_deviation",
        "customer_type_count", "customer_velocity_24h", "card_velocity_24h",
    ]
    type_counts = Counter(
        evidence_by_id[transaction_id]["transaction_type"]
        for transaction_id in flagged_ids
    )
    missingness = data_profile["missingness"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"""# Phase 4.2 — AI/ML Anomaly Detection Proof of Concept

## A. Objective

This isolated proof of concept adds unsupervised behavioral anomaly enrichment
without modifying the deterministic R001–R016 engine, alert persistence, case
workflow, frontend, or database. It does not predict fraud or money laundering.
The anomaly score means **higher score = more unusual relative to prior
observed behavior**.

Dataset used: `{dataset.as_posix()}`. The file is a development/evaluation
extract and was not modified.

## B. Dataset profile

| Metric | Observed value |
|---|---|
| Transactions | {data_profile['transactions']:,} |
| Date range | {data_profile['date_min']} to {data_profile['date_max']} |
| Date span | {data_profile['history_days']} days |
| Unique customers | {data_profile['unique_customers']:,} |
| Unique cards | {data_profile['unique_cards']:,} |
| Optional fields with any values | {', '.join(data_profile['optional_columns_present']) or 'None'} |

Transaction types:

{md_table([[str(k), f"{v:,}"] for k, v in data_profile['transaction_types'].items()], ['Transaction type', 'Count'])}

Statuses:

{md_table([[str(k), f"{v:,}"] for k, v in data_profile['statuses'].items()], ['Status', 'Count'])}

Amount statistics:

{md_table([[k, f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"] for k, v in data_profile['amount_statistics'].items()], ['Statistic', 'Value'])}

Missing fields with null values:

{md_table([[k, f"{v:,}"] for k, v in missingness.items()], ['Field', 'Missing rows']) if missingness else 'No null values observed.'}

The extract contains only the observed fields and one short reporting period.
No labels were created. `REVERSED` was retained as its own status and was not
converted to `DECLINED`.

## C. Feature engineering

Features are calculated in transaction-date order using only information
available before each transaction:

{md_table([[name, reason] for name, reason in [
    ("amount", "Raw transaction amount."),
    ("log_amount", "Reduces skew from large amounts."),
    ("customer_count / card_count", "Prior activity volume for each entity."),
    ("customer_total_amount / card_total_amount", "Prior cumulative value."),
    ("customer_mean_amount / card_mean_amount", "Prior average amount baseline."),
    ("customer_amount_deviation / card_amount_deviation", "Difference from prior entity baseline."),
    ("customer_type_count", "Prior count of this transaction type for the customer."),
    ("customer_velocity_24h / card_velocity_24h", "Prior events in the preceding 24-hour window."),
]], ['Feature', 'Purpose'])}

Feature vector used by Isolation Forest:
`{", ".join(feature_names)}`.

No country, home-currency, domestic-status, load-source, settlement-currency,
or originating-country-currency feature was used because those fields are
absent from the supplied report.

## D. Cold-start handling

An observation is eligible only when it has a customer ID, card number,
timestamp, numeric amount, and at least {MIN_HISTORY} prior transactions for
both the customer and card. Ineligible observations receive no anomaly score
and are reported as history-insufficient. They are not assigned a fabricated
zero or probability.

## E. Model choice

Isolation Forest was selected as a practical unsupervised outlier detector for
multivariate behavioral features when no confirmed fraud/AML labels exist. It
does not produce a fraud probability and was not evaluated as a classifier.

## F. Model configuration

| Setting | Value |
|---|---|
| Algorithm | `sklearn.ensemble.IsolationForest` |
| Estimators | {N_ESTIMATORS} |
| Random seed | {RANDOM_SEED} |
| Contamination assumption | {CONTAMINATION} |
| Minimum history | {MIN_HISTORY} prior customer and card transactions |
| Velocity window | {VELOCITY_WINDOW_HOURS} hours |
| Preprocessing | Numeric historical features; no labels; no synthetic rows |
| Score direction | Higher `anomaly_score` means more unusual |

The contamination value is a model operating assumption for selecting a small
candidate set. It is not an estimate of fraud prevalence.

## G. Results

| Metric | Result |
|---|---|
| Eligible transactions scored | {len(eligible):,} |
| Excluded for insufficient history/data | {len(scored) - len(eligible):,} |
| Flagged by Isolation Forest | {len(flagged):,} |
| Minimum anomaly score | {eligible.anomaly_score.min():.4f} |
| Median anomaly score | {eligible.anomaly_score.median():.4f} |
| Maximum anomaly score | {eligible.anomaly_score.max():.4f} |

Flagged counts by transaction type:

{md_table([[str(k), f"{v:,}"] for k, v in type_counts.items()], ['Transaction type', 'Anomaly flags']) if type_counts else 'No eligible flags.'}

## H. Top anomaly examples

These are unusual-behavior candidates, not fraudulent transactions:

{md_table(examples, ['Transaction ID', 'Type', 'Amount', 'Score', 'ML flag', 'Existing rule trigger', 'Evidence summary']) if examples else 'No eligible examples.'}

The examples expose only the transaction identifier and behavioral evidence
needed for this POC. They do not expose full card or customer identifiers.

## I. Relationship with existing 16-rule alerts

The existing `RuleEngine` was run in memory against the same transaction
objects. This did not persist alerts or mutate the database. The comparison is
an overlap analysis, not a classification evaluation:

| Group | Count |
|---|---:|
| Existing rule-triggered transaction IDs (eligible comparison population) | {len(comparable_rule_ids):,} |
| Rule-triggered and ML-flagged | {both:,} |
| Rule-triggered but not ML-flagged | {rule_only:,} |
| ML-flagged but not rule-triggered | {ml_only:,} |
| Neither in the eligible comparison | {neither:,} |

An ML-only flag is complementary behavioral evidence, not an alert or
fraud label. A rule-only result remains fully valid even when the anomaly model
does not flag it.

## J. Limitations

- The report spans only {data_profile['history_days']} days; it is not enough
  to validate six- or twelve-month AML behavior.
- No fraud, AML, investigation, or case-outcome labels exist.
- The model was not evaluated with accuracy, precision, recall, F1, ROC-AUC,
  or any other supervised metric.
- The feature set is limited to fields genuinely present in the CSV.
- Cold-start transactions are intentionally unscored.
- Isolation Forest is sensitive to feature quality, scale, contamination
  assumptions, and the population represented in an upload.
- Rule-triggered transactions were not treated as labels.
- This POC is not integrated into FastAPI and produces no operational alerts.

## K. Recommended next step

Keep the POC as an isolated enrichment experiment. Before integration, add
validated historical ingestion, data-quality/coverage reporting, analyst
review of candidates, score stability checks across new files, and a separately
stored enrichment result. Preserve deterministic rules as the authoritative
alert layer.

## L. Interview explanation

- **What AI did you implement?** An unsupervised behavioral anomaly-enrichment
  POC using Isolation Forest.
- **What model and why?** Isolation Forest, because there are no confirmed
  labels and it can identify multivariate outliers without fabricating classes.
- **Was it supervised?** No, it was unsupervised.
- **Where did training data come from?** The supplied immutable transaction CSV;
  features were built from prior observed transactions in that file.
- **Did you have fraud labels?** No. Existing rule triggers were never used as
  fraud labels.
- **How did you evaluate it?** Reproducibility, feature coverage, cold-start
  handling, score distribution, representative examples, and overlap with
  deterministic rule triggers. This is not an accuracy evaluation.
- **How is it different from the AML rules?** Rules apply explicit configured
  conditions; the model identifies unusual combinations in observed behavior.
- **Can it make the final AML decision?** No. It is enrichment only; rules and
  analysts own the operational decision.
- **What happens for a new CSV?** Validate and profile it, build only supported
  historical features, leave cold-start rows unscored, fit/score under the
  documented configuration, and present candidates alongside—not instead of—
  deterministic rule alerts.

## Reproducibility

Run from the project root with the configured environment:

```text
.venv-1\\Scripts\\python.exe scripts\\phase_4_2_ml_poc.py
```

This command reads the source CSV and writes this report only. It does not
write `aml.db`, call FastAPI, persist alerts, or modify rule configuration.
The eligible per-transaction enrichment output is written to
`docs/PHASE_4_2_ML_POC_SCORES.csv`.
""", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    frame, transactions = load_transactions(args.dataset)
    data_profile = profile(frame)
    feature_frame, evidence = historical_features(transactions)
    feature_names = [column for column in feature_frame.columns if column not in {"transaction_id"}]
    eligible_mask = feature_frame["customer_count"].ge(MIN_HISTORY) & feature_frame["card_count"].ge(MIN_HISTORY)
    feature_frame["history_sufficient"] = eligible_mask
    feature_frame["anomaly_score"] = np.nan
    feature_frame["anomaly_flag"] = False
    eligible = feature_frame.loc[eligible_mask, feature_names].replace([np.inf, -np.inf], np.nan).dropna()
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    if len(eligible) >= 2:
        model.fit(eligible)
        scores = -model.decision_function(eligible)
        flags = model.predict(eligible) == -1
        feature_frame.loc[eligible.index, "anomaly_score"] = scores
        feature_frame.loc[eligible.index, "anomaly_flag"] = flags
    rule_ids = rule_trigger_ids(transactions)
    build_report(args.dataset, args.report, data_profile, feature_frame, evidence, rule_ids)
    write_scores(args.output, feature_frame, evidence)
    print(f"Report written to {args.report}")
    print(f"Scores written to {args.output}")
    print(f"Transactions: {len(transactions)}")
    print(f"Eligible: {int(feature_frame['history_sufficient'].sum())}")
    print(f"Flagged: {int(feature_frame['anomaly_flag'].sum())}")
    print(f"Rule-triggered transaction IDs: {len(rule_ids)}")


if __name__ == "__main__":
    main()
