# Phase 4.2 — AI/ML Anomaly Detection Proof of Concept

## A. Objective

This isolated proof of concept adds unsupervised behavioral anomaly enrichment
without modifying the deterministic R001–R016 engine, alert persistence, case
workflow, frontend, or database. It does not predict fraud or money laundering.
The anomaly score means **higher score = more unusual relative to prior
observed behavior**.

Dataset used: `data/raw/OXYGPRPPAU_TransactionReport_2025-05-12_to_2025-05-18.csv`. The file is a development/evaluation
extract and was not modified.

## B. Dataset profile

| Metric | Observed value |
|---|---|
| Transactions | 15,034 |
| Date range | 2025-05-12 00:04:35 to 2025-05-18 23:57:23 |
| Date span | 6 days |
| Unique customers | 1,352 |
| Unique cards | 1,357 |
| Optional fields with any values | None |

Transaction types:

| Transaction type | Count |
|---|---|
| POS | 8,715 |
| LOAD | 3,885 |
| ATM | 1,240 |
| ECOM | 813 |
| ATM_BALANCE_ENQUIRY | 122 |
| CARD_TO_CARD | 80 |
| ATM_INSUFF_DECLINE_FEE | 56 |
| ATM_INVALID_PIN_DECLINE_FEE | 49 |
| REFUND | 21 |
| ECOM_REVERSAL | 15 |
| POS_REVERSAL | 13 |
| ATM_REVERSAL | 12 |
| FUNDPOST_CREDIT | 8 |
| FUNDPOST_DEBIT | 4 |
| LOAD_REVERSAL | 1 |

Statuses:

| Status | Count |
|---|---|
| PAYMENT_SUCCESS | 14,995 |
| REVERSED | 39 |

Amount statistics:

| Statistic | Value |
|---|---|
| count | 15,034 |
| min | 0.01 |
| median | 38.45 |
| mean | 184.09 |
| max | 17,328.64 |

Missing fields with null values:

| Field | Missing rows |
|---|---|
| rrn | 3,966 |
| auth_code | 3,980 |
| other_party_id | 15 |
| other_party_name | 14 |
| description | 11,042 |
| mcc | 3,992 |
| home_currency | 15,034 |
| country_code | 15,034 |
| domestic_status | 15,034 |
| load_source | 15,034 |
| settlement_currency | 15,034 |
| originating_country_currency | 15,034 |

The extract contains only the observed fields and one short reporting period.
No labels were created. `REVERSED` was retained as its own status and was not
converted to `DECLINED`.

## C. Feature engineering

Features are calculated in transaction-date order using only information
available before each transaction:

| Feature | Purpose |
|---|---|
| amount | Raw transaction amount. |
| log_amount | Reduces skew from large amounts. |
| customer_count / card_count | Prior activity volume for each entity. |
| customer_total_amount / card_total_amount | Prior cumulative value. |
| customer_mean_amount / card_mean_amount | Prior average amount baseline. |
| customer_amount_deviation / card_amount_deviation | Difference from prior entity baseline. |
| customer_type_count | Prior count of this transaction type for the customer. |
| customer_velocity_24h / card_velocity_24h | Prior events in the preceding 24-hour window. |

Feature vector used by Isolation Forest:
`amount, log_amount, customer_count, card_count, customer_total_amount, card_total_amount, customer_mean_amount, card_mean_amount, customer_amount_deviation, card_amount_deviation, customer_type_count, customer_velocity_24h, card_velocity_24h`.

No country, home-currency, domestic-status, load-source, settlement-currency,
or originating-country-currency feature was used because those fields are
absent from the supplied report.

## D. Cold-start handling

An observation is eligible only when it has a customer ID, card number,
timestamp, numeric amount, and at least 5 prior transactions for
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
| Estimators | 200 |
| Random seed | 42 |
| Contamination assumption | 0.02 |
| Minimum history | 5 prior customer and card transactions |
| Velocity window | 24 hours |
| Preprocessing | Numeric historical features; no labels; no synthetic rows |
| Score direction | Higher `anomaly_score` means more unusual |

The contamination value is a model operating assumption for selecting a small
candidate set. It is not an estimate of fraud prevalence.

## G. Results

| Metric | Result |
|---|---|
| Eligible transactions scored | 9,351 |
| Excluded for insufficient history/data | 5,683 |
| Flagged by Isolation Forest | 187 |
| Minimum anomaly score | -0.2608 |
| Median anomaly score | -0.2129 |
| Maximum anomaly score | 0.1110 |

Flagged counts by transaction type:

| Transaction type | Anomaly flags |
|---|---|
| POS_REVERSAL | 1 |
| POS | 52 |
| ATM | 103 |
| LOAD | 22 |
| CARD_TO_CARD | 2 |
| ECOM | 5 |
| ATM_REVERSAL | 2 |

## H. Top anomaly examples

These are unusual-behavior candidates, not fraudulent transactions:

| Transaction ID | Type | Amount | Score | ML flag | Existing rule trigger | Evidence summary |
|---|---|---|---|---|---|---|
| 1004 | ATM | 2000.00 | 0.1110 | Yes | No | customer history=12, card history=12, 24h velocity=2/2 |
| 2858 | ATM | 2000.00 | 0.1089 | Yes | Yes | customer history=11, card history=11, 24h velocity=4/4 |
| 4827 | ATM | 2000.00 | 0.0916 | Yes | Yes | customer history=7, card history=7, 24h velocity=2/2 |
| 2761 | ATM | 2000.00 | 0.0905 | Yes | No | customer history=32, card history=32, 24h velocity=5/5 |
| 5092 | ATM | 1000.00 | 0.0897 | Yes | Yes | customer history=5, card history=5, 24h velocity=3/3 |

The examples expose only the transaction identifier and behavioral evidence
needed for this POC. They do not expose full card or customer identifiers.

## I. Relationship with existing 16-rule alerts

The existing `RuleEngine` was run in memory against the same transaction
objects. This did not persist alerts or mutate the database. The comparison is
an overlap analysis, not a classification evaluation:

| Group | Count |
|---|---:|
| Existing rule-triggered transaction IDs (eligible comparison population) | 3,265 |
| Rule-triggered and ML-flagged | 102 |
| Rule-triggered but not ML-flagged | 3,163 |
| ML-flagged but not rule-triggered | 85 |
| Neither in the eligible comparison | 6,001 |

An ML-only flag is complementary behavioral evidence, not an alert or
fraud label. A rule-only result remains fully valid even when the anomaly model
does not flag it.

## J. Limitations

- The report spans only 6 days; it is not enough
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
.venv-1\Scripts\python.exe scripts\phase_4_2_ml_poc.py
```

This command reads the source CSV and writes this report only. It does not
write `aml.db`, call FastAPI, persist alerts, or modify rule configuration.
The eligible per-transaction enrichment output is written to
`docs/PHASE_4_2_ML_POC_SCORES.csv`.
