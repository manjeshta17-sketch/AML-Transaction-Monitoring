# Phase 4.3 — AI/ML Evaluation and Explainable Alert Enrichment POC

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
| Transactions in supplied extract | 15,034 |
| ML-eligible transactions with scores | 9,351 |
| ML-flagged transactions | 187 |
| ML anomaly + existing rule trigger | 102 |
| ML anomaly + no existing rule trigger | 85 |
| Existing rule trigger + no ML anomaly | 3,163 |
| Normal/non-anomalous comparison population | 6,001 |

The extract covers six days and has no confirmed fraud, AML, investigation, or
case-outcome labels. Rule triggers were used only as context, never as labels.

## 3. Representative transactions and generated evidence

Customer and card identifiers are masked in this report and the compact CSV.
All other values below are taken from the supplied transaction data and the
computed historical features.

| cohort | transaction_id | customer_id | card_number | txn_date | transaction_type | amount | anomaly_score | anomaly_flag | customer_history_count | card_history_count | customer_historical_average | card_historical_average | customer_amount_deviation | card_amount_deviation | customer_velocity_24h | card_velocity_24h | customer_type_count | rule_codes | explanation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML anomaly + existing rule trigger | 2858 | 2768...3487 | 4424...7064 | 2025-05-17 11:32:09 | ATM | 2000.00 | 0.1089 | True | 11 | 11 | 971.05 | 971.05 | 1028.95 | 1028.95 | 4 | 4 | 1 | R003 | Transaction amount 2000.00 was more than twice the customer historical average (971.05); amount was more than twice the card historical average (971.05); the preceding 24-hour window already contained 4/4 customer/card transactions. |
| ML anomaly + no existing rule trigger | 1004 | 2768...3487 | 4424...7064 | 2025-05-18 10:16:23 | ATM | 2000.00 | 0.1110 | True | 12 | 12 | 1056.79 | 1056.79 | 943.21 | 943.21 | 2 | 2 | 2 | None | Transaction amount 2000.00 differed from the customer/card historical averages (1056.79/1056.79); prior history was 12/12 transactions and 24-hour velocity was 2/2. |
| Existing rule trigger + no ML anomaly | 4073 | 6033...0487 | 4424...5067 | 2025-05-17 01:40:08 | LOAD | 1139.49 | -0.0002 | False | 28 | 28 | 62.32 | 62.32 | 1077.17 | 1077.17 | 7 | 7 | 1 | R003 | Transaction amount 1139.49 was more than twice the customer historical average (62.32); amount was more than twice the card historical average (62.32); the preceding 24-hour window already contained 7/7 customer/card transactions. |
| Normal/non-anomalous comparison | 7766 | 8235...5925 | 4424...0662 | 2025-05-15 05:22:33 | POS | 2.55 | -0.2213 | False | 6 | 6 | 19.60 | 19.60 | -17.05 | -17.05 | 3 | 3 | 6 | None | Transaction amount 2.55 was materially below the customer historical average (19.60); amount was materially below the card historical average (19.60); the preceding 24-hour window already contained 3/3 customer/card transactions. |

The explanations are deterministic templates based on actual amount baselines
and velocity values. No LLM or causal inference was used. “Unusual” describes
the model-relative behavior only; it does not mean illicit activity.

## 4. ML-only analysis

The 85 ML-only flags are distributed as follows:

| transaction_type | count | min_amount | max_amount |
|---|---|---|---|
| POS | 42 | 0.01 | 325.02 |
| ATM | 37 | 100.0 | 2003.25 |
| ECOM | 5 | 5.41 | 1092.3 |
| POS_REVERSAL | 1 | 4.5 | 4.5 |

ML-only amount range: **0.01 to 2003.25**
when rows are present. The number of customers with more than one ML-only flag
is **13**, and the number of cards with more than one ML-only
flag is **13**.

The concentration is therefore primarily transaction-type-specific, especially
where the observed amount and historical behavior combination is unusual. The
results provide potentially useful additional monitoring signals, but they do
not establish missed fraud or missed AML cases. The model has no labels or
causal evidence with which to make that claim.

## 5. Rule-only analysis

The 3,163 rule-only eligible rows demonstrate why deterministic
rules must remain authoritative. Rule-only rows were generated by configured
conditions such as explicit thresholds or repeated merchant activity, while
the behavioral model did not flag them as multivariate outliers. Rule-only
context by code:

| rule_code | rule_only_rows |
|---|---|
| R002 | 2 |
| R003 | 3162 |

The selected rule-only example is evidence of a deterministic rule signal that
should not be replaced merely because the ML score is normal. A normal ML
score means only that the transaction was not isolated by this model and
feature population.

## 6. Does ML add useful complementary information?

| Question | Evidence-based conclusion |
|---|---|
| Does ML add information beyond deterministic rules? | Yes, in this POC it produces 85 eligible ML-only candidates, including behavior not selected by the configured rule triggers. This is complementary signal evidence, not case-outcome validation. |
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
