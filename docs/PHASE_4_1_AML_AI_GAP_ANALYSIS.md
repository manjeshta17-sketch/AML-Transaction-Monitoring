# Phase 4.1 — Existing AML Rule System and AI/ML Gap Analysis

## 1. Purpose and scope

This document analyzes the existing deterministic AML rule system and identifies
the smallest credible AI/ML/LLM contribution for a later phase. It does not
implement models, LLM features, rules, APIs, schema changes, or frontend
features.

The intended workflow is:

```text
New CSV transaction file
        ↓
Import and validation
        ↓
Evaluate configured AML rules
        ↓
Generate rule-based alerts
        ↓
Analyst investigation and case
```

The supplied OXYGPRPPAU report is a development/evaluation extract, not a
production data contract or a permanent project outcome.

### Evidence labels used in this document

- **Available now**: directly represented in the current model/imported extract.
- **Missing/insufficient**: required by a rule but absent, incomplete, or too
  short in the supplied extract.
- **Observed implementation**: behavior verified from the current rule engine,
  configuration service, schemas, or checkpoint.
- **Proposed/future**: a design option that is not currently implemented.

## 2. Sources inspected

- [AGENTS.md](../AGENTS.md)
- [PHASE_2_COMPLETE_CHECKPOINT.md](../PHASE_2_COMPLETE_CHECKPOINT.md)
- [rule_engine.py](../backend/app/services/rule_engine.py)
- [rule.py](../backend/app/schemas/rule.py)
- [transaction.py](../backend/app/models/transaction.py)
- [alert.py](../backend/app/models/alert.py)
- [transaction_service.py](../backend/app/services/transaction_service.py)
- [rule-status-mapping.md](./rule-status-mapping.md)
- Supplied immutable report:
  `data/raw/OXYGPRPPAU_TransactionReport_2025-05-12_to_2025-05-18.csv`

The CSV has two metadata rows followed by a pipe-delimited header. Its supplied
columns are:

`Txn Date`, `Corporate Name`, `Proxy Card Number`, `Card Number`, `RRN`,
`Auth Code`, `Ext Txn Id`, `Amount`, `TransactionType`, `Status`, `Customer Id`,
`Post Wallet Balance`, `CR/DR Flag`, `Other Party Id`, `Other Party Name`,
`Currency`, `Product`, `Txn Amount`, `Fees`, `Description`, `mcc`,
`ActivationDate`.

The importer also recognizes optional columns:
`Home Currency`, `Country Code`, `Domestic Status`, `Load Source`,
`Settlement Currency`, and `Originating Country Currency`. They are not present
in the supplied report and are stored as null when absent.

## 3. Current data and implementation baseline

The Phase 2 checkpoint reports the following evaluation baseline for the
immutable development extract:

- 15,034 transactions
- 6,144 persisted alerts
- R001: 6 alerts
- R002: 4 alerts
- R003: 6,124 alerts
- R015: 10 alerts

These counts are historical observations for this extract only. They are not
model predictions, production targets, or expected results for a future upload.

The alert model stores the rule code/name, transaction, risk level, priority,
status, and assignment. Rule evaluation returns ordinary triggers separately
from insufficient-history and data-insufficient diagnostics. Only ordinary
triggers are eligible for alert persistence.

The current implementation distinguishes `REVERSED` from `DECLINED`.
`REVERSED` is not silently treated as a declined transaction. Reversal-labelled
transaction types and decline-fee-labelled types are also not assumed to mean
the same thing as a canonical decline.

## 4. Rule-by-rule gap analysis

| Rule code | Rule name/description | Detection purpose | Required attributes | Available in current dataset? | Current implementation status | Configurable parameters | What the rule can detect | Known limitation | Potential enhancement |
|---|---|---|---|---|---|---|---|---|---|
| R001 | High-value card load | Detect a single `LOAD` above a threshold. | `transaction_type`, numeric `amount`. | **YES**: `TransactionType` and `Amount` are present. | Enabled; single-transaction rule; ordinary triggers become alerts. | Load type; amount threshold, default 5,000. | High-value loads in the uploaded file. | It is a threshold rule, not a behavioral baseline; it does not establish intent or fraud. | Add a separate behavioral enrichment score using customer/card history; retain R001 as the transparent trigger. |
| R002 | Repeated declined or reversal-related merchant activity | Detect more than the configured qualifying count at one merchant within a time window. | Merchant identifier (`other_party_id` by default), `txn_date`, status and/or reversal suffix. | **PARTIAL**: merchant ID, date, status and transaction type are present; no literal `DECLINED` status. | Enabled; windowed rule with an inclusive one-hour window. `REVERSED` and `_REVERSAL` qualify according to configuration; they are not aliases for `DECLINED`. | Merchant field; count threshold 3; window 60 minutes; qualifying statuses `DECLINED`, `REVERSED`; reversal suffix `_REVERSAL`. | Repeated reversed/reversal-labelled activity and any future canonical declined activity represented in a compatible file. | It cannot prove declined card-purchase behavior when the source has no canonical decline semantics; merchant identifiers can be missing or ambiguous. | Obtain a documented decline outcome/status taxonomy and improve merchant normalization; use statistical velocity as enrichment, not replacement. |
| R003 | Repeated successful merchant activity | Detect more than the configured number of successful transactions at one merchant within a time window. | Merchant identifier, `txn_date`, successful status. | **YES/PARTIAL**: fields are present; merchant quality depends on source values. | Enabled; windowed rule with an inclusive one-hour window. | Merchant field; count threshold 3; window 60 minutes; qualifying status `PAYMENT_SUCCESS`. | Short-window bursts of successful activity at one merchant. | High volume is not inherently suspicious; the rule lacks customer/peer context and may generate many operational alerts. | Add customer/card baseline and peer comparison to prioritize or explain bursts while keeping the rule trigger deterministic. |
| R004 | Unusual declined or reversal card purchase activity | Detect unusual decline/reversal purchase behavior against a per-card historical baseline. | Canonical decline outcome, explicit card-purchase indicator, card identifier, transaction date, historical per-card baseline. | **NO/PARTIAL**: no canonical `DECLINED`, no explicit card-purchase semantic sufficient for this rule, and only one week of data. | Defined but deliberately disabled with `DATA_INSUFFICIENT`. It does not generate alerts. | Implementation status, required data, and explicit status mapping. | Nothing in the current run because it is disabled; a future complete feed could support unusual card-purchase outcome behavior. | `REVERSED` must not be substituted for `DECLINED`; no reliable baseline exists. | Add source-level decline semantics and sufficient history; validate the baseline definition before enabling. |
| R005 | Unusual card loading amount | Compare each current card load with the average individual load amount in prior months. | `LOAD`, configured grouping field (`card_number`), `amount`, `txn_date`, six prior calendar months by default. | **PARTIAL/NO**: card, amount, type and date exist; the report covers one week, not six prior months. | Enabled historical rule; returns insufficient-history diagnostics where months are unavailable, not alerts. | Grouping field; lookback months 6; increase percentage 100%. | A load materially above a card’s established historical individual-load average when history exists. | One week cannot validate a six-month history; missing amounts would also prevent a reliable baseline. | Build a history window from multiple validated uploads or an approved warehouse; add robust statistics and minimum-observation requirements. |
| R006 | Monthly loading value above historical average | Compare current monthly card load total with the average total of the prior 12 months. | `LOAD`, grouping field, numeric `amount`, `txn_date`, twelve prior calendar months. | **PARTIAL/NO**: core fields exist, but twelve-month history is absent. | Enabled historical rule; insufficient-history diagnostics are produced instead of fabricated alerts. | Grouping field; lookback months 12; increase percentage 50%. | A current monthly load-value surge against a complete prior-month baseline. | A one-week extract cannot support the required baseline; monthly totals also depend on complete ingestion. | Add rolling historical storage and data-completeness checks; compare against seasonality only after enough history exists. |
| R007 | Monthly loading frequency above historical average | Compare current monthly `LOAD` count with the prior six-month average. | `LOAD`, grouping field, `txn_date`, six prior calendar months. | **PARTIAL/NO**: fields exist, history does not. | Enabled historical rule; insufficient-history diagnostics are not persisted as alerts. | Grouping field; lookback months 6; increase percentage 50%. | A monthly load-frequency increase after a complete history is available. | Cannot distinguish a genuine behavioral change from an incomplete extract or reporting-period boundary. | Add ingestion completeness metadata and a minimum-history gate; use change-point or seasonal analysis as optional enrichment. |
| R008 | International POS transaction outside home currency | Detect a high-value POS transaction whose currency differs from the explicit home currency. | `transaction_type=POS`, numeric `amount`, transaction `currency`, explicit `home_currency`. | **PARTIAL/NO**: POS, amount, and generic currency exist; `home_currency` is absent. | Enabled data-dependent rule; missing home currency produces a data-insufficient diagnostic, not an alert. | Type POS; amount threshold 999; home-currency field. | Cross-currency POS activity when home currency is explicitly supplied. | Generic `Currency` cannot be used as a home-currency proxy; it cannot establish internationality in this extract. | Require explicit home currency from the source or a governed customer/account reference; add FX context only as enrichment. |
| R009 | International ATM transaction outside home currency | Detect a high-value ATM transaction whose currency differs from explicit home currency. | `transaction_type=ATM`, numeric `amount`, transaction currency, explicit `home_currency`. | **PARTIAL/NO**: ATM, amount, and generic currency exist; home currency is absent. | Enabled data-dependent rule; missing home currency produces a diagnostic. | Type ATM; amount threshold 999; home-currency field. | Cross-currency ATM activity with explicit home-currency evidence. | Same proxy and data-quality limitation as R008. | Govern home-currency sourcing and add location/FX evidence only when explicitly available. |
| R010 | International POS transaction involving a high-risk country | Detect POS transactions involving a configured high-risk/blocked country. | `transaction_type=POS`, explicit `country_code`, configured high-risk country list. | **NO**: `country_code` is absent; the default configured list is empty. | Enabled data-dependent rule; missing country produces a diagnostic and no alert. | Type POS; country field; normalized high-risk country list. | Country-list matches once explicit country evidence and a non-empty governed list exist. | Cannot infer country from merchant name, currency, or other fields; an empty list cannot identify high-risk countries. | Introduce a versioned, governed country-risk reference and explicit transaction-country sourcing; keep list provenance visible. |
| R011 | International ATM transaction involving a high-risk country | Detect ATM transactions involving a configured high-risk/blocked country. | `transaction_type=ATM`, explicit `country_code`, configured high-risk country list. | **NO**: country absent and default list empty. | Enabled data-dependent rule; diagnostic only for the supplied extract. | Type ATM; country field; normalized high-risk country list. | Country-list matches with explicit country evidence and configuration. | Same inference and empty-list limitation as R010. | Use governed country data and source-quality checks; do not infer country from currency. |
| R012 | Different countries on the same card within twelve hours | Detect geographic inconsistency for one card in a time window. | `card_number`, explicit `country_code`, `txn_date`. | **NO/PARTIAL**: card and date exist; country is absent. | Enabled data-dependent rule; missing card/country/timestamp evidence produces a diagnostic. | Grouping field; country field; twelve-hour window. | A later transaction on the same card with a different explicit country within the window. | It is a data-consistency signal, not proof of travel or compromise; no country means no evaluation. | Add reliable country/location provenance and optionally compare elapsed time/distance only with appropriate location evidence. |
| R013 | Increased frequency of domestic ATM transactions | Compare latest observed month’s domestic ATM count with the prior six-month average. | `transaction_type=ATM`, grouping field, `domestic_status`, `txn_date`. | **NO/PARTIAL**: ATM, card and date exist; `domestic_status` is absent. | Enabled data-dependent historical rule; missing domestic field produces a diagnostic. | Type ATM; grouping field; six-month lookback; 50% increase; domestic field and allowed values `DOMESTIC`. | Domestic ATM frequency change when explicit domestic classification and history exist. | Currency is never a domestic proxy; one week lacks history and domestic classification. | Source an explicit domestic/international classification and combine with account baseline after completeness checks. |
| R014 | Only source of load is C2C transfer | Detect entities whose loads in the three-month lookback all have an explicit C2C source. | `LOAD`, grouping field, `txn_date`, explicit `load_source`. | **NO/PARTIAL**: load/card/date may exist; `load_source` is absent. | Enabled data-dependent rule; missing source evidence produces a diagnostic. | Grouping field; three-month lookback; load-source field; C2C values `C2C`. | A narrow source-concentration pattern when every relevant load has explicit source evidence. | Transaction type alone is not proof of source; one week lacks the lookback and source field. | Add governed source taxonomy and show evidence coverage; consider source concentration as an enrichment feature. |
| R015 | High-value card-to-card transfer | Detect a `CARD_TO_CARD` transaction above a threshold. | `transaction_type`, numeric `amount`. | **YES**: fields are present. | Enabled; single-transaction rule; ordinary triggers become alerts. | Type `CARD_TO_CARD`; amount threshold 1,000. | High-value C2C transactions in the uploaded file. | It does not establish whether the transfer is suspicious without sender/recipient relationship and behavioral context. | Add entity relationship and baseline features for prioritization, while retaining the transparent threshold trigger. |
| R016 | Unusual dynamic currency conversion | Detect a difference between settlement currency and originating-country currency. | Explicit `settlement_currency`, explicit `originating_country_currency`. | **NO**: both optional fields are absent. | Enabled data-dependent rule; missing fields produce a diagnostic, not an alert. | Settlement-currency field; originating-country-currency field. | Explicit currency-conversion mismatch when both fields are present. | Generic transaction currency cannot substitute for either field; mismatch alone is not proof of wrongdoing. | Require source-level currency fields and add FX-rate/context checks only after data provenance is established. |

## 5. What the current system can and cannot detect

### It can detect now, when the required core fields are present

- Single-transaction amount thresholds for `LOAD` and `CARD_TO_CARD`.
- Merchant-window activity using explicit merchant identifiers and timestamps.
- Successful-transaction bursts using the configured `PAYMENT_SUCCESS` status.
- Reversal/reversal-labelled merchant activity under R002’s explicit
  configuration.
- Rule-based risk level and priority attached to each generated alert.
- Idempotent alert persistence keyed by transaction and rule.
- Alert-to-case investigation workflow.

### It cannot reliably detect in the supplied extract

- Canonical declined card-purchase behavior.
- Six- and twelve-month customer/card historical changes.
- Country-based risk or impossible-travel patterns.
- Domestic versus international behavior based on explicit location fields.
- Home-currency comparisons.
- C2C load-source concentration.
- Dynamic currency conversion from explicit settlement/originating fields.
- Fraud or money laundering as a confirmed outcome.
- Model accuracy, because no labeled fraud/AML ground truth is established.

The one-week report is also insufficient for claims about long-term behavior.
Missing values must remain missing; they must not be inferred from generic
currency, merchant text, transaction type, or reversal status.

## 6. AI/ML opportunity matrix

| Capability | Why it is useful | Input data required | Available now? | Recommended approach | Expected output | Should it affect final AML decision? |
|---|---|---|---|---|---|---|
| Customer behavioral baseline | Provides context for whether a transaction is unusual for a customer/card. | Repeated uploads or history; customer/card ID; amount, type, time, merchant; sufficient history. | **PARTIAL**: identifiers and core fields exist, but the supplied report is one week. | Rolling descriptive statistics first: median, robust deviation, count/value by time period. | Baseline features and deviation percentages. | No direct decision; use for analyst context and prioritization. |
| Transaction anomaly detection | Finds unusual combinations not covered by fixed thresholds. | Numeric amount, frequency, time features, transaction type, merchant/customer features; enough observations. | **PARTIAL**. | Isolation Forest as an unsupervised benchmark, with feature scaling and contamination sensitivity checks; compare with robust z-scores. | Anomaly score and top contributing features where explainable. | No; enrichment only. |
| Velocity/burst detection | Detects bursts across dimensions beyond a single merchant window. | Event timestamps, customer/card/merchant identifiers, transaction status and type. | **YES for core fields**, subject to data quality. | Explicit rolling-window counts and rates, or a simple unsupervised feature layer; do not duplicate R002/R003 without a distinct scope. | Burst features and prioritization signal. | No; deterministic rules remain authoritative. |
| Peer-group anomaly detection | Compares behavior with similar merchants, customers, or transaction types. | Stable peer attributes, enough peer population, amount/frequency distributions. | **PARTIAL/NO**: peer definitions and stable history are not established. | Robust peer-group percentiles or clustering only after a defensible peer definition. | Peer deviation score. | No; analyst support only. |
| Alert prioritization | Helps analysts review high-volume rule alerts first. | Alert rule/risk/priority, transaction context, feature scores, later analyst outcomes. | **PARTIAL**: alert context exists; labels do not. | Start with transparent weighted triage using deterministic features; later evaluate a calibrated model only with labeled outcomes. | Ranked queue or priority recommendation with reasons. | It may recommend review order, not final disposition. |
| Risk scoring | Combines rule and behavioral evidence consistently. | Rule signals, data completeness, anomaly features, customer/account context, outcome labels for supervised calibration. | **PARTIAL**. | Begin with a transparent additive score and confidence/data-coverage indicators; do not call it probability without calibration. | Enrichment score and evidence coverage. | No automatic final AML decision. |
| Multiple-rule correlation | Highlights entities affected by several independent signals. | Alert history joined by customer/card/merchant/time; rule codes and timestamps. | **PARTIAL**: current alert model supports rule context, but history is not a labeled outcome. | Deterministic correlation graph/window features before ML. | Correlated-alert summary and escalation cue. | No; analyst/case prioritization only. |
| Customer/transaction profiling | Gives investigators a compact behavioral profile. | Customer/card history, transaction mix, amounts, counterparties, time and geography where available. | **PARTIAL**. | Feature aggregation and descriptive profiling; avoid opaque segmentation until data coverage is demonstrated. | Profile attributes and trend summaries. | No. |
| Alert explanation | Makes deterministic and statistical signals understandable. | Rule parameters, triggering transaction, relevant comparison window, data-insufficiency diagnostics. | **YES for rule evidence**; ML explanations depend on later features. | Template-based explanations first; optional grounded LLM paraphrase with structured evidence. | Evidence-linked explanation, not a new conclusion. | No. |
| Case summarization | Reduces repetitive analyst writing. | Alert, transaction, case status, comments, rule evidence. | **YES for current case workflow**. | Grounded LLM summarization with strict source citations/field references and no unsupported inference. | Draft case summary and open questions. | No; analyst owns the case decision. |
| Analyst investigation assistant | Supports questions over known evidence. | Retrieved transaction/alert/case records and rule definitions; access controls and audit logging. | **PARTIAL**: records exist; assistant infrastructure does not. | Retrieval-grounded LLM with constrained tools, refusal on missing evidence, and explicit source references. | Answers, evidence links, and suggested next checks. | No. |

### ML model choice

The minimum defensible model contribution is an unsupervised anomaly-enrichment
component, not a fraud classifier. A practical first comparison is:

1. Robust descriptive baselines (median, percentile, median absolute deviation,
   rolling counts and values).
2. Isolation Forest for multivariate outlier scoring when there are enough
   observations and stable features.
3. Optional clustering only if peer groups can be defined and validated.

Deep learning is not justified by the current data volume, missing fields,
one-week extract, or absence of labels. No accuracy claim should be made.
Evaluation should focus on stability, feature coverage, sensitivity analysis,
analyst review, and whether the enrichment adds useful prioritization beyond
existing rule alerts.

## 7. Recommended target architecture

```text
Existing deterministic rules
        ↓
Rule-based alerts
        ↓
AI/ML enrichment
        ↓
Risk/priority enrichment
        ↓
LLM investigation assistance
        ↓
Analyst decision
        ↓
Case
```

### Decision ownership

- **Deterministic rule layer** owns explicit rule conditions, thresholds,
  required-data checks, rule risk level, configured priority, and alert
  generation.
- **AI/ML enrichment layer** owns anomaly scores, behavioral deviations,
  peer/burst features, and evidence coverage. It does not create an unsupported
  accusation.
- **Risk/priority enrichment layer** may recommend a review order or add a
  transparent enrichment score. It must not silently overwrite the
  deterministic alert decision.
- **LLM layer** owns evidence-grounded explanation, summarization, and
  question answering. It must cite the records and rule evidence it used,
  state when data is missing, and refuse unsupported conclusions.
- **Analyst** owns interpretation, investigation, escalation, disposition, and
  case outcome.
- **Case workflow** records the analyst’s operational work; it is not an
  automatic model verdict.

## 8. Demonstration scenario for a new transaction CSV

The demonstration must use a new upload and report measured results at runtime.
No future numerical result should be pre-filled.

1. **Transactions received**: display the importer’s actual inserted-record
   count and, where available, the upload validation message. Duplicates are
   currently skipped by `ext_txn_id`; the import response currently exposes
   only `records_imported`, not a separate skipped count.
2. **Validation result**: show success or the backend’s safe validation error.
   The current contract is a pipe-delimited CSV with two metadata rows and the
   required report columns.
3. **R001–R016 evaluation**: run configured monitoring and display actual
   alerts plus insufficient-history/data diagnostics. A diagnostic is not an
   alert.
4. **Alerts grouped by rule**: use the returned rule codes/counts and persisted
   alert records; do not derive counts from assumptions.
5. **Severity/risk**: display the configured alert risk level and priority.
6. **AI/ML enrichment**: calculate only features supported by the uploaded
   file and available retained history. If required history or fields are
   absent, state that enrichment is unavailable or low coverage.
7. **Analyst explanation**: explain the deterministic trigger and any
   enrichment evidence using templates or a grounded LLM; include missing-data
   caveats.
8. **Case workflow**: allow an analyst to investigate and create/use a case
   from a real alert. The analyst, not the model, makes the case decision.

The demo should explicitly include a new-file scenario that exercises
duplicates, malformed/missing required columns, and a valid file, but it must
not insert fabricated rows or claim a successful model outcome without runtime
evidence.

## 9. Smallest credible Phase 4 implementation

### Recommended minimum

1. Preserve R001–R016 and the existing alert/case workflow unchanged.
2. Add a measured data-quality and feature-coverage report per upload:
   available columns, null rates for rule-required fields, date range, and
   history sufficiency.
3. Add a transparent behavioral enrichment service using:
   - rolling transaction count/value features,
   - customer/card baseline deviations when history exists,
   - burst/velocity features distinct from R002/R003,
   - an Isolation Forest score only when minimum data and feature coverage
     thresholds are met.
4. Store or return enrichment evidence separately from deterministic rule
   alerts; do not turn an anomaly score into a fraud label.
5. Add template-based alert explanations first.
6. Add one grounded LLM use case: draft an alert/case summary from retrieved
   transaction, alert, rule, and case evidence, with explicit source fields and
   missing-data statements.
7. Evaluate without ground-truth claims:
   - feature coverage and missingness,
   - score stability across uploads,
   - sensitivity to contamination/threshold settings,
   - overlap and complementarity with deterministic alerts,
   - analyst usefulness through a documented review rubric.

### Interview-ready answers

- **What AI did you implement?** An unsupervised anomaly-enrichment layer that
  adds behavioral deviation and, when justified by data coverage, an Isolation
  Forest anomaly score to deterministic alerts.
- **What ML model did you use?** Isolation Forest as an unsupervised outlier
  detector, compared with robust statistical baselines.
- **Why that model?** There is no established fraud/AML label set, behavior is
  heterogeneous, and the project needs a practical unsupervised benchmark
  rather than a fabricated classifier.
- **What was the training data?** Historical transaction behavior available in
  the project database and subsequent validated uploads, subject to explicit
  minimum-history and feature-coverage checks. The supplied one-week extract
  alone is not sufficient for long-horizon rules or a production model.
- **How did you evaluate it?** Coverage, stability, sensitivity analysis,
  deterministic-alert complementarity, and analyst review—not accuracy or
  precision claims without labeled outcomes.
- **How is it different from the existing rule engine?** Rules apply explicit,
  explainable conditions and generate alerts; ML identifies deviations from
  observed behavior without replacing those conditions.
- **Where did the LLM help?** Grounded alert explanation, case summarization,
  and analyst Q&A over retrieved evidence.
- **Does the AI make the final AML decision?** No. The deterministic system
  supplies alerts, AI supplies enrichment, and the analyst owns the decision.
- **What happens when a completely new CSV is uploaded?** The file is validated
  against the existing contract, imported, evaluated by R001–R016, and
  produces runtime alert and data-insufficiency results. AI enrichment runs
  only for supported fields/history; otherwise the system reports the
  limitation rather than fabricating a score.

## 10. Conclusion

The existing platform already provides a meaningful deterministic foundation:
configurable rules, explicit risk/priority, alert idempotency, data-insufficient
diagnostics, and analyst cases. Its largest gaps are not a lack of more rules,
but limited historical depth, absent optional location/currency/source fields,
ambiguous outcome semantics, and no labeled outcomes for supervised learning.

The most credible contribution is therefore a bounded enrichment and
explanation layer. It should improve context and analyst efficiency while
leaving deterministic alert generation and the final AML decision with the
existing rule and analyst workflow.
