# Phase 4.5 — AI/ML/LLM Production Integration Design

## 1. Purpose and phase boundary

This document designs, but does not implement, the production integration of
the Phase 4.2 Isolation Forest POC and the Phase 4.4 grounded LLM assistant.
It does not change FastAPI, database models, services, rules, alerts, cases,
monitoring behavior, or the frontend.

The design preserves the existing ownership model:

- R001-R016 remain the authoritative deterministic monitoring rules.
- `MonitoringService` evaluates transactions and persists rule-triggered alerts.
- `AlertService` owns alert creation and deduplication by transaction/rule.
- `CaseService` creates and manages cases from existing alerts.
- AI components enrich analyst context; they do not become decision engines.

The POCs are not production integrations yet. The Phase 4.2 script is an
isolated feature/model experiment, and the Phase 4.4 script is an
offline-first prompt/evidence experiment.

## 2. Sources and observed integration points

The design was based on:

- [PHASE_4_1_AML_AI_GAP_ANALYSIS.md](./PHASE_4_1_AML_AI_GAP_ANALYSIS.md)
- [PHASE_4_2_ML_POC_REPORT.md](./PHASE_4_2_ML_POC_REPORT.md)
- [PHASE_4_3_ML_EVALUATION_REPORT.md](./PHASE_4_3_ML_EVALUATION_REPORT.md)
- [PHASE_4_4_LLM_POC_REPORT.md](./PHASE_4_4_LLM_POC_REPORT.md)
- [transaction_service.py](../backend/app/services/transaction_service.py)
- [monitoring_service.py](../backend/app/services/monitoring_service.py)
- [alert_service.py](../backend/app/services/alert_service.py)
- [case_service.py](../backend/app/services/case_service.py)
- [rule_configuration_service.py](../backend/app/services/rule_configuration_service.py)
- [alert.py](../backend/app/models/alert.py)
- [case.py](../backend/app/models/case.py)
- [transaction.py](../backend/app/models/transaction.py)

Observed current behavior:

1. CSV import validates the required pipe-delimited report columns, normalizes
   values, skips duplicate `ext_txn_id` values, and commits transactions.
2. Monitoring loads configured rules, evaluates all persisted transactions,
   creates alerts for ordinary rule triggers, commits, and reports
   insufficient-history/data-insufficient diagnostics.
3. Alerts retain rule code/name, transaction reference, risk level, priority,
   status, and assignment. Alert identity is unique for a transaction/rule
   pair.
4. Cases reference an alert and have their own status, priority, assignment,
   comments, and lifecycle.
5. Rule configuration is JSON-validated and constrained to known rule codes
   and safe model fields.

## 3. Recommended target architecture

```text
New CSV file
    |
    v
Validate and normalize import
    |
    v
Persist transactions
    |
    v
Evaluate configured R001-R016
    |
    +------------------------------+
    |                              |
    v                              v
Persist deterministic alerts   Record rule diagnostics
    |
    v
Build historical behavioral features
    |
    v
Score eligible transactions with versioned Isolation Forest
    |
    v
Persist or associate AI enrichment
    |
    v
Prepare bounded, structured alert evidence
    |
    v
Optional LLM investigation assistance
    |
    v
Analyst review and existing case workflow
```

The deterministic branch must complete independently of both AI branches. AI
failure must not roll back valid imports or rule alerts.

### Decision boundaries

| Component | Owns | Explicitly does not own |
|---|---|---|
| R001-R016 | Configured deterministic detection and rule-trigger result | ML scoring, LLM interpretation, final analyst outcome |
| Alert service | Creation, identity, status, priority, and assignment of rule alerts | Deciding whether ML or LLM evidence is true or false |
| ML enrichment | Unusual-behavior score, flag, history sufficiency, evidence features | Fraud probability, alert suppression, rule override, case closure |
| LLM assistant | Grounded summary, evidence organization, missing-data statement, analyst checks | Fraud/AML decision, alert lifecycle, rule interpretation changes |
| Analyst | Investigation judgment and case actions | Treating AI output as authoritative proof |

## 4. End-to-end data flow

### 4.1 Transaction to rule evaluation

The existing importer remains the source of normalized transaction attributes:
transaction ID, external transaction ID, date, customer/card identifiers,
amount, type, status, merchant fields, currency fields, and optional fields.
The importer must continue to reject malformed/missing required columns and
must preserve `REVERSED` as distinct from `DECLINED`.

The monitoring service then supplies persisted transactions and the active
configured rule definitions to the existing rule engine. The engine returns:

- ordinary `RuleTriggerResult` values;
- `InsufficientHistoryResult` values; and
- `DataInsufficientResult` values.

Only ordinary triggers create deterministic alerts. AI processing must consume
this result rather than reimplementing or changing rule semantics.

### 4.2 Rule result to alert

For each ordinary trigger, the existing alert identity remains:

```text
transaction_id + rule_code
```

The alert retains its current rule code/name, risk level, priority, status,
assignment, and transaction relationship. ML may later attach context to this
alert, but it cannot change the trigger, risk level, priority, status, or
deduplication behavior unless a separately approved product decision changes
those existing contracts.

### 4.3 Alert/transaction to ML enrichment

The ML feature stage receives:

- the current transaction;
- prior transactions for the same customer and card, ordered by timestamp;
- supported transaction-type and velocity history;
- the immutable model artifact and feature-pipeline version.

It produces a transaction-level enrichment. The alert context can reference
that enrichment by transaction ID. For an alert with multiple relevant
transactions in a future design, the evidence selection must be explicit and
bounded; it must not silently send an entire customer history to an LLM.

### 4.4 Alert to LLM evidence

The LLM preparation stage is a deterministic serializer, not a database dump.
It selects and validates:

- alert ID/code if available;
- rule code, name, and relevant validated parameters;
- the triggering transaction facts;
- bounded relevant historical statistics or transaction summaries;
- ML score, flag, model version, and evidence features when available;
- explicit missing-data and history-sufficiency statements.

It must not send raw CSV files, arbitrary filesystem content, secrets, or
unbounded transaction history. The resulting JSON is the only model input.

## 5. ML integration design

### 5.1 Location of the pipeline

When implementation is approved, extract the reusable Phase 4.2 logic into a
dedicated service/module under `backend/app/services/`, for example:

```text
backend/app/services/ml/
    feature_pipeline.py
    anomaly_model.py
    enrichment_service.py
    model_registry.py
```

The existing isolated script should remain a reproducibility/reference
artifact, while production code should call the shared feature pipeline rather
than maintain a second incompatible implementation.

### 5.2 When features are generated

The preferred sequence is:

1. Import and commit normalized transactions.
2. Run deterministic monitoring and commit rule alerts.
3. Run ML enrichment as a separate best-effort stage over the newly imported
   population and required prior history.
4. Associate results with transactions/alerts without changing rule results.

This separation prevents an ML exception from invalidating a successful
deterministic monitoring run. A later asynchronous job may be preferable for
large files, but the job status must be observable and must not block access
to rule alerts.

### 5.3 Feature and history policy

Reuse the Phase 4.2 features:

- amount and log amount;
- prior customer/card counts and cumulative amounts;
- prior customer/card averages and deviations;
- prior customer transaction-type count;
- prior customer/card 24-hour velocity.

Features must be computed using only data available before the transaction.
The minimum history remains five prior customer transactions and five prior
card transactions, plus valid customer/card IDs, timestamp, and amount.

For a new customer or card, missing IDs, invalid timestamp, invalid amount, or
insufficient history:

```text
history_sufficiency = "insufficient"
anomaly_score = null
anomaly_flag = null
evidence = {available facts and reason for no score}
```

No zero score or false flag may be used as a cold-start substitute.

### 5.4 Model loading and versioning

Production should load a read-only, immutable model artifact through a
controlled model registry or configured artifact path. The registry record
should include:

- model version;
- feature-pipeline version;
- training/build timestamp;
- estimator configuration;
- contamination assumption;
- random seed;
- artifact checksum;
- supported input schema;
- approval/status metadata.

The Phase 4.2 reference configuration is 200 estimators, seed 42,
contamination 0.02, and higher score meaning more unusual. Contamination is a
selection assumption, not fraud prevalence.

If the model artifact, checksum, feature version, or schema is missing or
incompatible, mark enrichment unavailable and continue deterministic
monitoring. Never silently run a different model under the same version.

### 5.5 Storage recommendation

Recommend a separate `transaction_ai_enrichments` record concept rather than
adding AI columns directly to `transactions` or `alerts`.

```text
transaction_ai_enrichments
  id
  transaction_id
  model_version
  feature_pipeline_version
  anomaly_score nullable
  anomaly_flag nullable
  history_sufficiency
  evidence_json
  generated_at
  status
  error_code nullable
```

An optional alert association can be represented by `alert_id` or resolved
through `transaction_id`, but the transaction-level result should remain
available to multiple rule alerts for that transaction.

Tradeoffs:

- **Transaction columns:** simple reads, but couple a reusable enrichment to
  the core transaction schema and make version history difficult.
- **Alert columns:** convenient for analysts, but duplicate the same ML result
  across multiple rule alerts and hide non-alert transaction enrichment.
- **Separate record:** supports versioning, retries, auditability, null
  outcomes, and reuse; it adds a join and requires lifecycle management.

The separate record is recommended. This is a proposal only; no schema change
is made in Phase 4.5.

### 5.6 Retraining and updates

Do not retrain on every upload. Establish a controlled batch process using
validated historical data, documented feature coverage, analyst review
feedback where available, and stability checks. A new artifact requires a new
model version, checksum, configuration record, and comparison against the
previous version. No confirmed labels means evaluation remains behavioral and
operational, not fraud accuracy.

## 6. Proposed alert enrichment contract

Conceptually, an alert detail response could expose:

```text
ai_enrichment:
  model_version: "phase-4.2-isolation-forest-v1"
  feature_pipeline_version: "behavioral-features-v1"
  anomaly_score: number | null
  anomaly_flag: boolean | null
  history_sufficiency: "sufficient" | "insufficient" | "unavailable"
  evidence:
    amount: number | null
    customer_historical_average: number | null
    card_historical_average: number | null
    customer_amount_deviation: number | null
    card_amount_deviation: number | null
    customer_history_count: integer | null
    card_history_count: integer | null
    customer_velocity_24h: integer | null
    card_velocity_24h: integer | null
    customer_same_type_prior_count: integer | null
  generated_at: timestamp | null
  status: "available" | "insufficient_history" | "unavailable" | "failed"
```

The UI should label this as **AI enrichment / unusual-behavior indicator**,
not risk-of-fraud or an AML conclusion. Deterministic rule information must be
shown separately and more authoritatively.

## 7. LLM integration design

### 7.1 Provider and invocation

Use the already evaluated provider approach only after explicit configuration
of an approved SDK, model, endpoint, timeout, and credential source. Secrets
must come from environment/configuration or a secret manager, never source
code or database rows.

The LLM call should be a bounded, on-demand analyst action from an alert
detail context, not an automatic replacement for monitoring. The core alert
page remains usable without it. A future implementation should record provider
and model version, request status, latency, and validation outcome without
logging raw prompts by default.

### 7.2 Structured input

The evidence-preparation service should create a strict allowlisted object:

```text
{
  alert: {id, alert_code, rule_code, rule_name, risk_level, priority},
  rule_evidence: {verified_parameters, trigger_description},
  transaction: {id, type, amount, timestamp, status, masked_identifiers},
  history: {bounded_statistics, relevant_recent_events_if_approved},
  ml_enrichment: {score, flag, history_sufficiency, evidence, model_version},
  data_availability: {available, missing, limitations}
}
```

Only fields verified by the application are included. Missing fields remain
missing; the serializer must not infer geography, currency, source of funds,
long-term history, or case outcomes.

### 7.3 Required output

The output contract remains exactly:

1. **Alert Summary** — what the supplied rule/transaction evidence says.
2. **Evidence** — concrete supplied facts, separated from interpretation.
3. **Missing Information** — unavailable fields, history, labels, or outcomes.
4. **Recommended Analyst Checks** — investigation questions and next checks.

The LLM must not say that fraud or money laundering occurred, close or
suppress an alert, reject a transaction, override a rule, or make a final
decision.

### 7.4 Grounding and validation

Use a strict system instruction plus a JSON-only evidence payload. Validate the
response before display:

- required headings exist and are in order;
- no unsupported facts are asserted;
- missing-information section is present;
- forbidden final-decision language is rejected or quarantined;
- response length and token limits are bounded;
- provider output is marked unvalidated until checks pass.

If validation fails, show the deterministic alert and evidence, report that AI
assistance was unavailable/invalid, and do not retry indefinitely. Analyst
recommendations remain suggestions, not workflow commands.

## 8. Failure handling and graceful degradation

| Failure | Required behavior |
|---|---|
| Malformed CSV | Reject import with existing validation error; do not run rules or AI on incomplete input. |
| Rule engine failure | Roll back the monitoring transaction as current behavior; surface the error. Do not create AI-only alerts. |
| ML model unavailable | Keep imported transactions and deterministic alerts; mark enrichment unavailable with a reason and continue. |
| Insufficient history | Store/display `history_sufficiency=insufficient`; keep score and flag null. |
| LLM provider unavailable/timeout | Keep alert and deterministic/ML evidence usable; mark assistance unavailable and allow retry. |
| LLM invalid or unsafe output | Do not display it as assistance; retain structured evidence and report validation failure. |
| Missing model version/checksum | Do not score; mark model configuration unavailable rather than using an unknown artifact. |
| Unsupported input schema | Reject the AI stage only; do not alter deterministic import/rule processing. |

The monitoring system must not make AI availability a prerequisite for
importing transactions, evaluating rules, creating alerts, or creating cases.

## 9. New-file processing sequence

For a file named `new_transactions.csv`, the logical flow is:

1. Receive the upload through the existing file-processing route.
2. Validate file type, metadata/header shape, required columns, parseability,
   and duplicate external transaction IDs.
3. Normalize dates, numeric values, and nulls using the existing importer.
4. Persist valid new transactions; report import outcome.
5. Run configured R001-R016 over persisted transactions.
6. Persist ordinary rule alerts with existing rule identity and lifecycle.
7. Return rule diagnostics for insufficient history or unavailable fields.
8. Run the versioned ML feature pipeline using prior eligible history.
9. Write available, insufficient-history, or unavailable enrichment outcomes.
10. Associate enrichment context with affected transaction/alert views.
11. When an analyst requests assistance, build an allowlisted evidence object.
12. Optionally call the configured LLM with that object only.
13. Validate the four-section response before display.
14. Let the analyst review evidence and use the existing alert-to-case workflow.

No numerical result is assumed for a future file. A new file can produce no
ML score for cold-start rows and can still produce valid deterministic alerts.

## 10. Analyst experience

An alert detail view should present distinct sections:

1. **Alert information:** alert code, status, priority, risk level, assignment.
2. **Deterministic rule:** rule code/name, configured parameters, and rule
   trigger evidence. This is authoritative and visually distinct.
3. **Transaction evidence:** date, type, amount, status, and necessary masked
   identifiers.
4. **Relevant history:** bounded customer/card counts, averages, deviations,
   transaction-type history, and velocity.
5. **ML enrichment:** score direction, flag, model/feature versions, history
   sufficiency, evidence, and unavailable status where applicable.
6. **AI investigation assistance:** clearly labelled generated assistance,
   four required sections, timestamp/provider/model, and validation status.
7. **Existing case workflow:** unchanged assignment, comments, status,
   priority, and case creation actions.

The analyst must never confuse generated narrative with a deterministic rule
result or a final disposition.

## 11. Security, privacy, and observability

### Security and privacy

- Never store credentials in source, prompts, reports, or database business
  fields.
- Use environment/configuration or a secret manager for provider credentials.
- Send only the allowlisted structured evidence object.
- Mask customer/card identifiers unless an approved investigation use requires
  a minimally necessary representation.
- Do not send raw CSVs, arbitrary filesystem content, or unrelated customers.
- Apply request size, timeout, retry, and retention controls.
- Do not log raw prompts, card numbers, customer identifiers, or full
  transaction histories by default.
- Treat provider output as untrusted text and escape it in the UI.

### Observability

Log structured operational metadata:

- import/monitoring/ML/LLM stage and correlation ID;
- model and feature-pipeline versions;
- provider/model name where applicable;
- processing status and failure category;
- latency and retry count;
- number of transactions/alerts/enrichments, without raw sensitive content;
- history-sufficiency counts;
- output validation status.

Provider errors should be summarized safely. Detailed sensitive payloads belong
in restricted diagnostics only when explicitly approved.

## 12. Interview explanation

**What exactly did you add?**  
An isolated Isolation Forest behavioral-enrichment POC and a grounded LLM
investigation-assistance POC. Phase 4.5 designs their production boundaries;
it does not integrate them yet.

**Why did you not use AI for the rule engine?**  
Rules provide auditable, configurable, deterministic AML controls. They remain
the authoritative detection and alert-generation layer.

**Why Isolation Forest?**  
The available data has no confirmed fraud labels. Isolation Forest identifies
unusual multivariate behavior without fabricating supervised labels.

**What does the LLM do?**  
It summarizes verified evidence, lists missing information, and suggests
analyst checks. It does not decide fraud, money laundering, alert status, or
case outcome.

**What happens when a new CSV is uploaded?**  
The existing importer validates and persists it, rules run first and create
deterministic alerts, then ML enriches eligible transactions. LLM assistance
is requested later from bounded structured alert evidence.

**What happens when AI is unavailable?**  
Imports, rule evaluation, alerts, and cases continue. ML or LLM availability is
reported as enrichment/assistance status, never as a reason to suppress core
monitoring.

**Can AI close an AML alert?**  
No. Only existing analyst-controlled alert/case workflows can change lifecycle
state.

**How do you prevent hallucinations?**  
Use an allowlisted JSON evidence object, explicit missing-data fields, strict
instructions, no raw filesystem access, bounded history, output validation,
and human review.

**How did you evaluate the ML model?**  
Phase 4.3 evaluated reproducible scores, cold-start handling, representative
evidence, and overlap/complementarity with rule triggers. It did not claim
fraud accuracy.

**How did you evaluate the LLM?**  
Phase 4.4 validated prompt grounding, required four-section structure,
missing-data handling, forbidden-decision checks, and offline-safe behavior.
No LLM classification accuracy was claimed.

## 13. Current implementation versus proposed integration

| Area | Currently implemented | Proposed, not implemented in Phase 4.5 |
|---|---|---|
| Deterministic rules/alerts/cases | Existing production workflow | Remains unchanged |
| ML features/model | Isolated Phase 4.2 script and score artifact | Shared service, immutable registry, versioned enrichment records |
| ML evaluation | Isolated Phase 4.3 report and examples | Operational stability and analyst-uplift evaluation |
| LLM evidence/prompt | Isolated offline Phase 4.4 script | On-demand provider adapter and alert-detail evidence preparation |
| LLM output validation | POC structural/forbidden-language checks | Production policy, audit, timeout, retention, and UI handling |
| API/database/frontend | Existing application only | Future explicitly reviewed integration changes |

## 14. Confirmation

This milestone created architecture documentation only. No application code,
FastAPI route, database model, rule, alert, case, frontend, ML integration,
LLM integration, package, or Phase 4.6+ functionality was added.
