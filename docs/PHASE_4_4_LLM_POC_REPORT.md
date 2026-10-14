# Phase 4.4 — LLM Investigation Assistant Proof of Concept

## 1. Scope

This isolated POC prepares structured AML evidence for an analyst-assistance
LLM. It does not integrate with FastAPI, the frontend, alerts, cases, the
database, monitoring, or the R001–R016 rule engine. It is not a chatbot and it
does not make a final AML or fraud decision.

The default execution is offline. It validates evidence preparation and prompt
construction without sending data to a provider. Live execution is available
only with `--live`, an existing `OPENAI_API_KEY`, and an installed OpenAI SDK.

## 2. Provider status

| Setting | Value |
|---|---|
| Default mode | Offline prompt/evidence validation |
| Live provider | OpenAI SDK only, if already configured |
| Model | `Not invoked in offline mode` |
| Credentials | Never stored, printed, or hard-coded |
| Generated at | `2026-10-07T09:45:58.684396+00:00` |

Run offline:

```text
.venv-1\Scripts\python.exe scripts\phase_4_4_llm_poc.py
```

Opt into a live call only when the environment is intentionally configured:

```text
.venv-1\Scripts\python.exe scripts\phase_4_4_llm_poc.py --live
```

## 3. Controlled input evidence structure

The input contains only verified fields from the Phase 4.3 selected examples:
transaction facts, masked identifiers, rule context when present, historical
feature values, ML evidence, and explicit availability limitations. It does
not include the raw CSV, arbitrary files, secrets, or unnecessary identifiers.

```json
{
  "rule": {
    "rule_code": "R003",
    "rule_name": "Repeated successful merchant activity",
    "rule_parameters": {
      "merchant_field": "other_party_id",
      "count_threshold": 3,
      "time_window_minutes": 60,
      "qualifying_statuses": ["PAYMENT_SUCCESS"]
    }
  },
  "transaction": {
    "transaction_id": 2858,
    "transaction_type": "ATM",
    "amount": 2000.0,
    "timestamp": "2025-05-17 11:32:09"
  },
  "ml_evidence": {
    "model_version": "phase-4.2-isolation-forest-v1",
    "anomaly_score": 0.1089,
    "anomaly_flag": true,
    "score_interpretation": "higher means more unusual relative to observed history"
  }
}
```

## 4. Strict prompt design

The system instruction requires four sections: Alert Summary, Evidence, Missing
Information, and Recommended Analyst Checks. It prohibits invented facts,
causal claims, fraud/AML conclusions, rule overrides, alert suppression, and
case closure. Anomaly scores must be described as unusual-behavior indicators,
not fraud probabilities.

Example exact user payload saved in
`docs/PHASE_4_4_LLM_TEST_PAYLOADS.json`:

```text
Prepare an analyst-assistance response from this JSON evidence only. Use exactly the four required headings and bullet facts under Evidence, Missing Information, and Recommended Analyst Checks. Do not add a final decision.

{
  "alert_id": null,
  "case_name": "Test 1 \u2014 rule-triggered + ML-anomalous",
  "data_availability": {
    "available": [
      "transaction amount, type, timestamp, masked customer/card identifiers",
      "historical customer/card counts and averages",
      "amount deviations and 24-hour velocity",
      "deterministic rule context when present",
      "Isolation Forest score and flag when eligible"
    ],
    "unavailable": [
      "alert ID and case outcome",
      "confirmed fraud or AML label",
      "investigation disposition",
      "country, home currency, domestic status, and load source",
      "validated six- or twelve-month history"
    ]
  },
  "historical_behavior": {
    "card_amount_deviation": 1028.9545454545453,
    "card_average_amount": 971.0454545454548,
    "card_transaction_count": 11,
    "card_velocity_24h": 4,
    "customer_amount_deviation": 1028.9545454545453,
    "customer_average_amount": 971.0454545454548,
    "customer_same_type_prior_count": 1,
    "customer_transaction_count": 11,
    "customer_velocity_24h": 4
  },
  "ml_evidence": {
    "anomaly_flag": true,
    "anomaly_score": 0.1089159936424488,
    "model_version": "phase-4.2-isolation-forest-v1",
    "score_interpretation": "higher means more unusual relative to observed history"
  },
  "rule": {
    "rule_code": "R003",
    "rule_name": "Repeated successful merchant activity",
    "rule_parameters": {
      "count_threshold": 3,
      "merchant_field": "other_party_id",
      "qualifying_statuses": [
        "PAYMENT_SUCCESS"
      ],
      "time_window_minutes": 60
    }
  },
  "transaction": {
    "amount": 2000.0,
    "card_identifier": "4424...7064",
    "customer_identifier": "2768...3487",
    "timestamp": "2025-05-17 11:32:09",
    "transaction_id": 2858,
    "transaction_type": "ATM"
  }
}
```

## 5. Test cases

| Test case | Rule context | ML context | Live output |
|---|---|---|---|
| Test 1 — rule-triggered + ML-anomalous | R003 | anomalous | prompt/evidence contract validated; no LLM response generated |
| Test 2 — rule-triggered + ML-normal | R003 | normal | prompt/evidence contract validated; no LLM response generated |
| Test 3 — ML-only anomalous | None | anomalous | prompt/evidence contract validated; no LLM response generated |

The tests are sourced from the deterministic Phase 4.3 examples:

1. Rule-triggered and ML-anomalous: R003 context plus anomaly evidence.
2. Rule-triggered and ML-normal: R003 context without an anomaly flag.
3. ML-only anomalous: anomaly evidence with no rule code.

The ML-only test explicitly includes unavailable merchant context and
source-of-funds information. The assistant must state those as missing rather
than inventing them.

## 6. Output contract and validation

Accepted live output must contain, in order:

1. `Alert Summary`
2. `Evidence`
3. `Missing Information`
4. `Recommended Analyst Checks`

The script rejects outputs containing final-decision language such as declaring
fraud, declaring money laundering, closing or suppressing an alert, or
rejecting a transaction. Offline mode does not pretend that an LLM response
was generated; it reports the exact structured payload and prompt instead.

## 7. Grounding and safety evaluation

- Evidence is constructed from the Phase 4.3 compact examples only.
- No raw CSV is sent to the model.
- No live call occurs unless explicitly requested.
- Missing geography, currency, long-term history, labels, investigation
  outcomes, and source-of-funds context remain explicit.
- Rule parameters are supplied only for the verified R003 examples.
- ML evidence includes score direction and model version.
- The LLM is advisory and cannot alter a rule, alert, case, or final decision.
- The POC uses no accuracy, precision, recall, or other LLM classification metric.

## 8. Limitations

- Offline mode validates payload construction, not model quality.
- No provider response can be assessed without intentionally configured
  credentials and a live call.
- A live response still requires human review and should be treated as
  assistance, not evidence beyond the supplied object.
- The source evidence covers only the Phase 4.2/4.3 development extract and
  lacks confirmed AML outcomes.
- Prompt validation is structural and safety-oriented; it is not a guarantee
  against every possible model failure.

## 9. Interview explanation

- **What AI did you implement?** A grounded LLM investigation-assistance POC
  that turns verified rule, transaction, historical, and ML evidence into a
  structured analyst response.
- **What does it decide?** Nothing final. It summarizes supplied facts,
  identifies missing information, and suggests checks.
- **How is it grounded?** The model receives a small JSON evidence object, not
  the filesystem or raw transaction CSV.
- **What happens when data is missing?** Missing fields are explicitly listed;
  the assistant is instructed not to infer them.
- **How does it relate to the rule engine and ML model?** Rules remain
  authoritative; ML remains an unusual-behavior indicator; the LLM explains
  and organizes evidence for an analyst.
- **What if the provider is unavailable?** The reproducible offline POC still
  validates the exact evidence and prompt payload without pretending a response
  exists.

## 10. Phase boundary confirmation

No production application code, API endpoint, frontend, alert/case behavior,
database schema, authentication, deployment, or Phase 4.5+ functionality was
implemented.
