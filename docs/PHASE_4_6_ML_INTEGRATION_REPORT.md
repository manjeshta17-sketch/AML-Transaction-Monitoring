# Phase 4.6 — Production ML Enrichment Integration Report

## 1. What was implemented

Phase 4.2's Isolation Forest was integrated as a transaction-level enrichment
stage after deterministic monitoring commits its rule alerts.

Implemented:

- Reusable backend ML service with the Phase 4.2 historical feature pipeline.
- Versioned local Isolation Forest artifact and metadata.
- Persistent `TransactionAIEnrichment` model.
- Explicit enrichment statuses:
  `AVAILABLE`, `INSUFFICIENT_HISTORY`, `UNAVAILABLE`, and `ERROR`.
- Read-only transaction enrichment endpoint.
- Focused tests for scoring, cold start, artifact failure, alert isolation,
  deterministic repeatability, and API access.

The ML stage does not create alerts, change rule ownership, change rule
priority, suppress alerts, close alerts, or alter case behavior.

## 2. Exact integration point

The existing `MonitoringService.run()` flow remains:

```text
load persisted rule configuration
    -> load transactions
    -> evaluate R001-R016
    -> create deterministic alerts
    -> commit deterministic monitoring transaction
    -> run ML enrichment as a separate best-effort stage
```

The ML call is after the existing deterministic `db.commit()`. If ML fails,
the deterministic monitoring result remains committed and the failure is
logged. Existing rule evaluation and alert creation were not rewritten.

## 3. ML feature pipeline reused from Phase 4.2

The reusable implementation is in
[ml_service.py](../backend/app/services/ml_service.py). The Phase 4.2 script
now imports this same `historical_features` implementation rather than
maintaining a second feature-generation copy.

The feature definitions remain:

- amount and log amount;
- prior customer/card transaction counts;
- prior customer/card cumulative amounts;
- prior customer/card mean amounts;
- customer/card amount deviations;
- prior customer transaction-type count;
- customer/card 24-hour velocity.

Features are calculated in transaction-date order using only prior
observations. The minimum-history policy remains five prior customer
transactions and five prior card transactions, with valid customer/card IDs,
timestamp, and amount required.

## 4. Model/version handling

The local development artifact is:

```text
backend/app/services/artifacts/phase-4.2-isolation-forest-v1.pkl
backend/app/services/artifacts/phase-4.2-isolation-forest-v1.json
```

Metadata validates:

- model version: `phase-4.2-isolation-forest-v1`;
- feature pipeline version: `behavioral-features-v1`;
- the exact 13 feature names;
- 200 estimators;
- contamination assumption `0.02`;
- random seed `42`.

The application loads this known artifact and does not train during uploads or
monitoring requests. The artifact is an unsupervised anomaly detector:
higher score means more unusual relative to observed history. It is not a
fraud probability or AML classification.

If the artifact or compatible metadata is unavailable, enrichment records are
written with `UNAVAILABLE`, null score, and null flag. Deterministic monitoring
continues normally.

## 5. Enrichment schema

The new transaction-level model is
[ai_enrichment.py](../backend/app/models/ai_enrichment.py):

```text
transaction_ai_enrichments
  transaction_id
  model_version
  feature_pipeline_version
  anomaly_score nullable
  anomaly_flag nullable
  history_sufficient
  enrichment_status
  evidence_json
  generated_at
```

The record is unique per transaction and is upserted on repeated monitoring
runs. Evidence is retained as JSON for analyst context. The separate
transaction-level record avoids duplicating one enrichment across multiple
rule alerts for the same transaction.

## 6. Cold-start behavior

Transactions without the required history receive:

```text
anomaly_score = null
anomaly_flag = null
history_sufficient = false
enrichment_status = INSUFFICIENT_HISTORY
```

They are not treated as normal and are not treated as anomalous. A model
artifact failure preserves `INSUFFICIENT_HISTORY` for cold-start rows and uses
`UNAVAILABLE` for rows that otherwise have sufficient history.

## 7. API added

Added read-only endpoint:

```text
GET /transactions/{transaction_id}/ai-enrichment
```

Response fields:

- `transaction_id`;
- `model_version`;
- `feature_pipeline_version`;
- `anomaly_score`;
- `anomaly_flag`;
- `history_sufficient`;
- `enrichment_status`;
- `generated_at`.

The endpoint does not redesign or change the existing alert API.

## 8. Tests added

Added [test_ml_enrichment.py](../tests/test_ml_enrichment.py), covering:

1. sufficient-history transaction receives available enrichment;
2. insufficient-history transaction receives null score and flag;
3. missing model artifact does not break deterministic monitoring;
4. ML enrichment does not create an alert;
5. ML enrichment does not change rule ownership;
6. repeated enrichment is deterministic for the same model/version/input;
7. the read-only API returns persisted enrichment;
8. missing enrichment returns a safe 404.

Existing monitoring and rule tests were run alongside the new focused tests.

## 9. Test results

Focused tests:

```text
12 passed, 2 warnings
```

Complete backend suite:

```text
106 passed, 2 warnings
```

The two warnings are the existing pandas date-format warnings from the
transaction importer.

The Phase 4.2 runner was also executed after the shared-pipeline refactor:

```text
Transactions: 15034
Eligible: 9351
Flagged: 187
Rule-triggered transaction IDs: 6137
```

## 10. Real CSV verification

The immutable development CSV was imported into an isolated in-memory SQLite
database. No production-like database was mutated.

Observed results:

| Result | Value |
|---|---:|
| Transactions imported | 15,034 |
| Transactions evaluated | 15,034 |
| Alerts generated | 6,144 |
| R001 alerts | 6 |
| R002 alerts | 4 |
| R003 alerts | 6,124 |
| R015 alerts | 10 |
| Enrichment records | 15,034 |
| Available enrichments | 9,351 |
| Insufficient-history enrichments | 5,683 |
| Model version | `phase-4.2-isolation-forest-v1` |

## 11. Confirmation that deterministic rule behavior/counts were unchanged

Confirmed. The real-CSV verification produced the same deterministic alert
counts as the established baseline:

```text
R001: 6
R002: 4
R003: 6,124
R015: 10
Total: 6,144
```

ML enrichment is additional transaction context only. It does not create
ML-only AML alerts, modify rule ownership, alter thresholds, change priorities,
or affect alert/case lifecycle.

## 12. Limitations

- The local artifact is a development artifact trained from the supplied
  Phase 4.2 extract; it is not a production-calibrated model.
- The source data covers only six days and has no confirmed fraud or AML
  labels.
- Cold-start transactions remain unscored.
- Country, home-currency, domestic-status, load-source, settlement-currency,
  and originating-country-currency fields are unavailable in the supplied
  extract.
- No LLM, analyst-assistance API, or frontend display was added.
- A future production deployment needs controlled artifact distribution,
  checksum/approval management, retention policy, and operational monitoring.
- No anomaly accuracy or fraud-detection accuracy is claimed.

## 13. Current architecture after Phase 4.6

```text
CSV import
    -> normalized transactions
    -> deterministic R001-R016 monitoring
    -> persisted rule alerts
    -> transaction-level ML enrichment
       - available score/flag when history and artifact permit
       - null score/flag for insufficient history
       - unavailable status when artifact cannot load
    -> existing analyst alert/case workflow
```

The LLM investigation-assistance layer remains a later phase and is not
integrated.

## 14. Interview-ready explanation

**What exactly did you add?**  
A reusable backend service that loads a versioned Isolation Forest artifact,
reuses the validated Phase 4.2 historical features, and persists
transaction-level anomaly enrichment after deterministic monitoring.

**Does the ML model create AML alerts?**  
No. R001-R016 remain authoritative. ML only adds score, flag, history
sufficiency, and evidence context.

**What happens for a new customer or card?**  
The transaction receives no fabricated score. It is stored as
`INSUFFICIENT_HISTORY` with null anomaly score and flag.

**What happens if the artifact is unavailable?**  
Deterministic monitoring and alert creation continue. Eligible transactions are
marked `UNAVAILABLE`; cold-start transactions remain `INSUFFICIENT_HISTORY`.

**How is the model version controlled?**  
The service validates a known artifact and metadata pair containing model
version, feature-pipeline version, feature names, and configuration.

**Can ML close or suppress an alert?**  
No. It has no authority over rule ownership, status, priority, alerts, or
cases.

## 15. Final implementation summary

- **Files created:** ML service, enrichment model/schema, versioned model
  artifact and metadata, focused tests, and this report.
- **Files modified:** monitoring integration, application model registration,
  transaction API route, and Phase 4.2 script to reuse the shared pipeline.
- **Packages installed:** none during Phase 4.6.
- **Tests:** focused tests and complete backend suite passed.
- **Deterministic alert counts changed:** no.
- **Rule engine files modified:** no.
- **LLM code added:** no.
- **Phase 4.7 or later work:** not implemented.
