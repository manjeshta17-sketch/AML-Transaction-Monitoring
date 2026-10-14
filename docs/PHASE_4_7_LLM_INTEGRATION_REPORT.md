# Phase 4.7 — Production LLM Analyst Assistance Report

## 1. Architecture

Phase 4.7 adds an optional analyst-assistance layer after deterministic alert
creation and Phase 4.6 transaction-level ML enrichment:

```text
existing alert
  -> verified alert/rule/transaction data
  -> optional ML enrichment
  -> bounded evidence object
  -> grounded provider prompt
  -> optional provider response
  -> structural/safety validation
  -> persisted assistance execution metadata
  -> analyst remains final decision-maker
```

The implementation does not change the alert model or alert workflow fields.
It does not create, suppress, close, reject, reprioritize, or override alerts.

## 2. Provider abstraction

[llm_service.py](../backend/app/services/llm_service.py) defines a small
`LLMProvider` protocol and `ProviderResult` contract. Provider outcomes are
explicit:

- `SUCCESS`
- `PROVIDER_UNAVAILABLE`
- `CREDENTIALS_UNAVAILABLE`
- `TIMEOUT`
- `ERROR`

An environment-configured `OpenAIProvider` is included. It reads
`OPENAI_API_KEY` and `OPENAI_MODEL` from the environment only. It does not
hard-code credentials and does not send data unless both the SDK and API key
are available.

The development environment was inspected and has:

- no importable `openai` package;
- no configured `OPENAI_API_KEY`.

Therefore no live provider call was performed and no response was fabricated.
The API returns an explicit unavailable status while deterministic alerts and
ML enrichment remain usable.

## 3. Bounded evidence object

The evidence builder uses only persisted application data:

- alert code;
- authoritative rule code and name;
- persisted, validated rule parameters;
- transaction ID, type, amount, currency, and timestamp;
- masked customer and card identifiers;
- at most ten related customer/card transaction summaries;
- historical counts, averages, deviations, and velocity when present in the
  Phase 4.6 ML enrichment evidence;
- ML score, flag, model version, status, and history sufficiency;
- explicit missing-information statements.

Identifiers are masked to their final four characters where practical.
Unbounded transaction history is not included. Raw CSV content, arbitrary
filesystem content, secrets, and unrestricted application data are never sent
to the provider. Missing geography, source-of-funds, merchant context, and
other unavailable fields remain missing rather than being inferred.

## 4. Prompt design

The system instruction is versioned as
`phase-4.7-grounded-assistance-v1` and requires exactly these headings, in
order:

1. `Alert Summary`
2. `Evidence`
3. `Missing Information`
4. `Recommended Analyst Checks`

It instructs the provider to:

- use only supplied structured evidence;
- distinguish facts from interpretation;
- preserve missing information;
- treat R001-R016 as authoritative;
- treat an ML score as an unusual-behavior indicator, not a fraud probability;
- avoid final AML/fraud conclusions;
- avoid claims that an alert is legitimate or fraudulent;
- recommend investigation checks only.

The user prompt contains serialized bounded JSON evidence and explicitly
prohibits adding a final decision.

## 5. Output validation

Provider text is never treated as trusted assistance automatically. Validation
checks:

- non-empty response;
- maximum response length of 12,000 characters;
- all four required headings;
- prescribed heading order;
- non-empty sections;
- obvious unsupported final-decision language, including claims of fraud or
  money laundering and instructions to close, suppress, or reject.

This is structural and keyword safety validation, not a claim of semantic
truth verification. Invalid output is persisted as `INVALID` metadata with no
generated response exposed as validated assistance.

## 6. Persistence

The focused [llm_assistance.py](../backend/app/models/llm_assistance.py) model
stores one execution record per generation request:

```text
alert_id
provider
model
prompt_version
response_status
validated
generated_response
generated_at
latency_ms
```

No API key, secret, raw CSV, or unrestricted prompt archive is stored. Valid
responses are stored for the execution record; unavailable and invalid
responses store no trusted generated response.

## 7. API

Added:

```text
POST /alerts/{alert_id}/ai-assistance
```

The endpoint:

1. retrieves the existing alert;
2. retrieves its transaction;
3. retrieves available Phase 4.6 ML enrichment;
4. loads verified rule configuration;
5. builds bounded evidence;
6. invokes the configured provider abstraction;
7. validates successful output;
8. persists execution metadata;
9. returns the assistance status and validated response metadata.

The endpoint does not modify alert status, priority, assignment, rule code,
case state, or deterministic alert counts.

## 8. Failure handling

| Condition | Result |
|---|---|
| Alert not found | Existing API-style 404 |
| Transaction missing | Explicit 404; no provider call |
| Provider SDK missing | `PROVIDER_UNAVAILABLE` |
| API key missing | `CREDENTIALS_UNAVAILABLE` |
| Provider timeout | `TIMEOUT` |
| Provider API/connection error | `ERROR` |
| Empty or malformed response | `INVALID` |
| Missing required section | `INVALID` |
| Forbidden decision language | `INVALID` |
| ML enrichment unavailable | Evidence states ML unavailable; request can continue |

Deterministic monitoring and Phase 4.6 ML enrichment are independent of this
optional request-time assistance path.

## 9. Security and privacy

Implemented safeguards include:

- credentials read only from environment configuration;
- masked customer/card identifiers;
- bounded related history capped at ten records;
- no raw CSV or arbitrary filesystem access;
- no secret persistence;
- provider errors returned without provider internals or credentials;
- provider/model/prompt version and latency persisted for observability;
- full prompts are not logged by the service.

## 10. Tests and results

Added [test_llm_assistance.py](../tests/test_llm_assistance.py) with
deterministic mock-provider coverage for:

1. verified rule evidence;
2. available ML enrichment;
3. unavailable-information reporting;
4. exclusion of raw CSV/filesystem content and unmasked identifiers;
5. unavailable provider;
6. successful provider response;
7. malformed response;
8. missing required section;
9. forbidden final-decision language;
10. unchanged alert status;
11. unchanged alert priority;
12. no alert creation/closure/suppression;
13. explicit missing SDK behavior.

Results:

```text
Phase 4.7 + ML focused tests: 17 passed
Complete backend suite: 116 passed, 2 existing pandas warnings
```

No live external LLM call was required or performed.

## 11. Deterministic rules unchanged

No R001-R016 rule-engine file was modified. LLM assistance consumes existing
alert/rule results and has no authority to alter their semantics, thresholds,
ownership, priority, status, or count.

## 12. ML enrichment unchanged

No ML scoring behavior, feature definition, artifact, cold-start policy, or
enrichment persistence behavior was changed. The assistance layer reads the
existing transaction-level enrichment when available and explicitly reports
when it is unavailable.

## 13. Limitations

- No live provider response was evaluated because the development environment
  has no OpenAI SDK or API key.
- Output validation detects obvious structural and final-decision violations;
  it does not prove factual truth or prevent every possible hallucination.
- Rule parameters are supplied from persisted configuration, but provider
  output quality depends on the configured model when one is later enabled.
- The current API returns generated assistance metadata; no frontend action or
  display was added in this phase.
- Provider selection is currently the optional OpenAI adapter; no additional
  provider was introduced.

## 14. Interview-ready explanation

**What exactly did you add?**  
A bounded, optional LLM assistance service that combines authoritative alert
evidence with available ML enrichment, sends only structured evidence to an
optional provider, validates the response, and persists its status.

**Can the LLM make the AML decision?**  
No. R001-R016 remain authoritative, ML remains enrichment, and the analyst
remains responsible for the final outcome. The LLM cannot close, suppress,
reject, or override an alert.

**How do you prevent hallucinations?**  
The provider receives a bounded JSON evidence object, not raw files or
unrestricted history. The system prompt prohibits invention and requires
missing information to be stated. Required sections, ordering, length, and
obvious final-decision language are validated before text is trusted.

**What happens when the provider is unavailable?**  
The request returns an explicit unavailable status. Existing alerts, cases,
deterministic monitoring, and ML enrichment continue normally.

**How is privacy handled?**  
Identifiers are masked, history is capped, raw CSVs and arbitrary filesystem
content are excluded, credentials are environment-only, and secrets are never
stored.

## 15. Current implementation status

- **Files created:** LLM persistence model, response schema, provider/evidence/
  prompt/validation service, focused tests, and this report.
- **Files modified:** application startup model registration and alert API
  route.
- **Packages installed:** none.
- **Tests:** 17 focused tests passed; 116 complete backend tests passed.
- **Deterministic alert counts changed:** no.
- **ML behavior changed:** no.
- **Rule engine files changed:** no.
- **Credentials created or stored:** no.
- **Live provider call performed:** no.
- **Frontend AI UI:** not implemented.
- **Retraining, model registry, and later phases:** not implemented.
