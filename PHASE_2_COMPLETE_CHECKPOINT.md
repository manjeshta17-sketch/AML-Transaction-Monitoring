# Phase 2 Complete Checkpoint

## Project

AML Transaction Monitoring

## Completed

### Phase 1

- AML backend foundation
- Transaction ingestion and transaction model
- R001-R016 rule definitions and implementation
- Alert generation and alert idempotency
- Case management and alert-to-case relationship
- Historical and data-insufficient handling
- Rule-engine architecture and classification refactor

### Phase 2

- Persistent rule configuration
- Alert management API
- Case management enhancement
- Transaction search and filtering
- Dashboard and monitoring APIs
- API validation and error handling
- Backend integration testing
- OpenAPI/API documentation

## Current verified real-data baseline

Using the immutable dataset:

`data/raw/OXYGPRPPAU_TransactionReport_2025-05-12_to_2025-05-18.csv`

- Transactions: 15,034
- Alerts: 6,144
- R001: 6
- R002: 4
- R003: 6,124
- R015: 10

## Current test baseline

Command:

```text
.venv-1\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Result:

- 99 passed
- 0 failed
- 0 skipped
- 2 pre-existing pandas date-format warnings

The suite includes 7 integration tests in
`tests/integration/test_backend_workflows.py`.

## Current project structure

- `backend/app/main.py`: FastAPI application entry point and startup setup
- `backend/app/api/`: HTTP route modules
- `backend/app/core/`: SQLAlchemy engine, sessions, migrations, and indexes
- `backend/app/models/`: SQLAlchemy models
- `backend/app/schemas/`: Pydantic request, response, rule, monitoring, and error schemas
- `backend/app/services/`: import, rule, monitoring, alert, case, dashboard, and configuration services
- `tests/`: unit, service, API, regression, OpenAPI contract, and integration tests
- `data/raw/`: immutable source reports
- `docs/`: rule documentation
- `notebooks/`: exploratory analysis
- `config/` and `.vscode/`: project configuration
- `aml.db`: local SQLite database used by the backend

## Important backend files

- `backend/app/services/transaction_service.py`
- `backend/app/services/rule_engine.py`
- `backend/app/services/monitoring_service.py`
- `backend/app/services/alert_service.py`
- `backend/app/services/case_service.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/services/rule_configuration_service.py`
- `backend/app/core/database.py`
- `backend/app/api/transactions.py`
- `backend/app/api/alerts.py`
- `backend/app/api/cases.py`
- `backend/app/api/dashboard.py`
- `backend/app/api/monitoring.py`
- `backend/app/api/rules.py`
- `backend/app/schemas/errors.py`

## Tests

The test directory contains 17 Python files, including:

- Existing rule-engine, transaction, alert, case, dashboard, and configuration tests
- `tests/test_api_error_handling.py`
- `tests/test_openapi_contract.py`
- `tests/integration/test_backend_workflows.py`

## Raw dataset location

- `data/raw/OXYGPRPPAU_TransactionReport_2025-05-12_to_2025-05-18.csv`
- `data/raw/OXYEXT_TransactionReport_2026-01-05_to_2026-01-11.xls`

Raw datasets are treated as immutable input.

## Known limitations and technical debt

- The project has no Git repository metadata or dependency manifest.
- The normal application database is a local SQLite file.
- Two pre-existing pandas warnings remain because transaction date formats are inferred during import.
- The supplied real CSV covers one week, so historical rules correctly report insufficient history rather than fabricating baselines.
- Some optional rule data fields are absent from the supplied CSV, so data-dependent rules may report data insufficiency.
- The API currently uses FastAPI's standard `/docs`, `/redoc`, and `/openapi.json` endpoints.

## Repository preservation status

- Git is not initialized in the project root.
- No commit was created because Git metadata is unavailable.
- No application behavior, AML rule, test, or dataset files were changed for this preservation check.
- This checkpoint file is the only file created by this check.

## Phase status

Phase 1 and Phase 2 are complete.

Phase 3 has **not** started.

## NEXT STEP

Phase 3 — Frontend / Product UI

Do not design or implement Phase 3 as part of this checkpoint.
