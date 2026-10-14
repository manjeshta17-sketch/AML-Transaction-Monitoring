"""Offline-first Phase 4.4 LLM investigation-assistant proof of concept.

The default execution prepares and validates structured evidence and prompts.
Live OpenAI execution is opt-in with --live and requires an existing
OPENAI_API_KEY plus the installed OpenAI SDK. No application data is sent by
the default run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "docs" / "PHASE_4_3_SELECTED_EXAMPLES.csv"
REPORT = PROJECT_ROOT / "docs" / "PHASE_4_4_LLM_POC_REPORT.md"
PAYLOADS = PROJECT_ROOT / "docs" / "PHASE_4_4_LLM_TEST_PAYLOADS.json"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_INSTRUCTION = """You are an AML investigation assistant.
Use only the structured evidence supplied by the user.
Do not invent facts, missing fields, geography, currency, history, or outcomes.
Distinguish directly supplied facts from cautious interpretation.
Explicitly state relevant missing information.
Treat deterministic rule results as authoritative evidence, but do not override,
suppress, close, or change them.
Treat anomaly scores as indicators of unusual behavior, never as fraud
probabilities.
Do not decide that fraud or money laundering occurred.
Do not recommend closing, rejecting, or suppressing an alert.
Return exactly these four headings:
Alert Summary
Evidence
Missing Information
Recommended Analyst Checks
Under Recommended Analyst Checks, suggest practical investigation checks and
questions without deciding the final AML outcome."""

SECTION_HEADERS = (
    "Alert Summary",
    "Evidence",
    "Missing Information",
    "Recommended Analyst Checks",
)
FORBIDDEN_DECISION_PATTERNS = (
    r"\bthis (transaction|alert|case) is fraudulent\b",
    r"\bthis is money laundering\b",
    r"\bclose the (alert|case)\b",
    r"\breject the transaction\b",
    r"\bsuppress the alert\b",
)


def as_optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def evidence_from_row(row: pd.Series, case_name: str) -> dict[str, Any]:
    rule_code = None if row["rule_codes"] in ("", "None") else row["rule_codes"]
    rule_details: dict[str, Any] | None = None
    if rule_code == "R003":
        rule_details = {
            "rule_code": "R003",
            "rule_name": "Repeated successful merchant activity",
            "rule_parameters": {
                "merchant_field": "other_party_id",
                "count_threshold": 3,
                "time_window_minutes": 60,
                "qualifying_statuses": ["PAYMENT_SUCCESS"],
            },
        }
    return {
        "case_name": case_name,
        "alert_id": None,
        "rule": rule_details,
        "transaction": {
            "transaction_id": int(row["transaction_id"]),
            "transaction_type": str(row["transaction_type"]),
            "amount": float(row["amount"]),
            "timestamp": str(row["txn_date"]),
            "customer_identifier": str(row["customer_id"]),
            "card_identifier": str(row["card_number"]),
        },
        "historical_behavior": {
            "customer_transaction_count": int(row["customer_history_count"]),
            "card_transaction_count": int(row["card_history_count"]),
            "customer_average_amount": float(row["customer_historical_average"]),
            "card_average_amount": float(row["card_historical_average"]),
            "customer_amount_deviation": float(row["customer_amount_deviation"]),
            "card_amount_deviation": float(row["card_amount_deviation"]),
            "customer_velocity_24h": int(row["customer_velocity_24h"]),
            "card_velocity_24h": int(row["card_velocity_24h"]),
            "customer_same_type_prior_count": int(row["customer_type_count"]),
        },
        "ml_evidence": {
            "model_version": "phase-4.2-isolation-forest-v1",
            "anomaly_score": as_optional_float(row["anomaly_score"]),
            "anomaly_flag": bool(row["anomaly_flag"]),
            "score_interpretation": "higher means more unusual relative to observed history",
        },
        "data_availability": {
            "available": [
                "transaction amount, type, timestamp, masked customer/card identifiers",
                "historical customer/card counts and averages",
                "amount deviations and 24-hour velocity",
                "deterministic rule context when present",
                "Isolation Forest score and flag when eligible",
            ],
            "unavailable": [
                "alert ID and case outcome",
                "confirmed fraud or AML label",
                "investigation disposition",
                "country, home currency, domestic status, and load source",
                "validated six- or twelve-month history",
            ],
        },
    }


def build_user_prompt(evidence: dict[str, Any]) -> str:
    return (
        "Prepare an analyst-assistance response from this JSON evidence only. "
        "Use exactly the four required headings and bullet facts under Evidence, "
        "Missing Information, and Recommended Analyst Checks. Do not add a "
        "final decision.\n\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
    )


def validate_response(text: str) -> list[str]:
    errors: list[str] = []
    positions = [text.find(f"## {header}") for header in SECTION_HEADERS]
    if any(position < 0 for position in positions):
        errors.append("Response is missing one or more required section headings.")
    elif positions != sorted(positions):
        errors.append("Required sections are not in the prescribed order.")
    for pattern in FORBIDDEN_DECISION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            errors.append(f"Forbidden final-decision language matched: {pattern}")
    return errors


def validate_prompt_contract(system: str, user: str) -> list[str]:
    errors: list[str] = []
    if any(header not in system for header in SECTION_HEADERS):
        errors.append("System instruction omits a required output heading.")
    if "Do not invent" not in system or "final AML" not in system:
        errors.append("System instruction is missing grounding or decision constraints.")
    if "data_availability" not in user or "Do not add a final decision." not in user:
        errors.append("User prompt omits availability evidence or decision constraint.")
    return errors


def live_completion(system: str, user: str, model: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if importlib.util.find_spec("openai") is None:
        raise RuntimeError("The OpenAI SDK is not installed.")
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The configured model returned empty content.")
    return content


def report_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| Test case | Rule context | ML context | Live output |", "|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['case_name']} | {row['rule_context']} | "
            f"{row['ml_context']} | {row['live_status']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Opt in to configured OpenAI execution.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    selected = pd.read_csv(EXAMPLES)
    expected = {
        "Test 1 — rule-triggered + ML-anomalous": "ML anomaly + existing rule trigger",
        "Test 2 — rule-triggered + ML-normal": "Existing rule trigger + no ML anomaly",
        "Test 3 — ML-only anomalous": "ML anomaly + no existing rule trigger",
    }
    inputs: list[dict[str, Any]] = []
    for case_name, cohort in expected.items():
        rows = selected[selected["cohort"] == cohort]
        if rows.empty:
            raise ValueError(f"Required cohort is absent from {EXAMPLES}: {cohort}")
        inputs.append(evidence_from_row(rows.iloc[0], case_name))

    # Explicitly exercise missing-data handling with the ML-only case; no
    # unavailable values are added to the evidence.
    inputs[2]["data_availability"]["unavailable"].append(
        "merchant context and source-of-funds information"
    )

    payloads: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []
    for evidence in inputs:
        user_prompt = build_user_prompt(evidence)
        result: dict[str, Any] = {
            "case_name": evidence["case_name"],
            "system_instruction": SYSTEM_INSTRUCTION,
            "user_prompt": user_prompt,
            "evidence": evidence,
            "live_output": None,
            "validation_errors": [],
        }
        prompt_errors = validate_prompt_contract(SYSTEM_INSTRUCTION, user_prompt)
        if args.live:
            try:
                result["live_output"] = live_completion(
                    SYSTEM_INSTRUCTION, user_prompt, args.model
                )
                result["validation_errors"] = validate_response(result["live_output"])
            except Exception as exc:
                result["live_output"] = None
                result["validation_errors"] = prompt_errors + [f"Live invocation unavailable: {exc}"]
        else:
            result["validation_errors"] = prompt_errors
        payloads.append(result)
        statuses.append({
            "case_name": evidence["case_name"],
            "rule_context": evidence["rule"]["rule_code"]
            if evidence["rule"]
            else "None",
            "ml_context": "anomalous"
            if evidence["ml_evidence"]["anomaly_flag"]
            else "normal",
            "live_status": "generated and validated"
            if result["live_output"] and not result["validation_errors"]
            else (
                "prompt/evidence contract validated; no LLM response generated"
                if not args.live and not result["validation_errors"]
                else "prompt/evidence validated; no accepted live output"
            ),
        })

    generated_at = datetime.now(timezone.utc).isoformat()
    PAYLOADS.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "mode": "live" if args.live else "offline",
                "model": args.model if args.live else None,
                "tests": payloads,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    prompt_example = payloads[0]["user_prompt"]
    report = f"""# Phase 4.4 — LLM Investigation Assistant Proof of Concept

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
| Model | `{args.model if args.live else 'Not invoked in offline mode'}` |
| Credentials | Never stored, printed, or hard-coded |
| Generated at | `{generated_at}` |

Run offline:

```text
.venv-1\\Scripts\\python.exe scripts\\phase_4_4_llm_poc.py
```

Opt into a live call only when the environment is intentionally configured:

```text
.venv-1\\Scripts\\python.exe scripts\\phase_4_4_llm_poc.py --live
```

## 3. Controlled input evidence structure

The input contains only verified fields from the Phase 4.3 selected examples:
transaction facts, masked identifiers, rule context when present, historical
feature values, ML evidence, and explicit availability limitations. It does
not include the raw CSV, arbitrary files, secrets, or unnecessary identifiers.

```json
{{
  "rule": {{
    "rule_code": "R003",
    "rule_name": "Repeated successful merchant activity",
    "rule_parameters": {{
      "merchant_field": "other_party_id",
      "count_threshold": 3,
      "time_window_minutes": 60,
      "qualifying_statuses": ["PAYMENT_SUCCESS"]
    }}
  }},
  "transaction": {{
    "transaction_id": 2858,
    "transaction_type": "ATM",
    "amount": 2000.0,
    "timestamp": "2025-05-17 11:32:09"
  }},
  "ml_evidence": {{
    "model_version": "phase-4.2-isolation-forest-v1",
    "anomaly_score": 0.1089,
    "anomaly_flag": true,
    "score_interpretation": "higher means more unusual relative to observed history"
  }}
}}
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
{prompt_example}
```

## 5. Test cases

{report_table(statuses)}

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
"""
    REPORT.write_text(report, encoding="utf-8")
    print(f"Report written to {REPORT}")
    print(f"Payloads written to {PAYLOADS}")
    print("Mode:", "live" if args.live else "offline")


if __name__ == "__main__":
    main()
