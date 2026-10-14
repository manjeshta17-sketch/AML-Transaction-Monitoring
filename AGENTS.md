# AML Transaction Monitoring

## Scope

This repository contains an early FastAPI backend for importing and monitoring
AML transaction data. Keep changes focused on the requested area and do not
modify raw source datasets unless explicitly asked.

## Layout

- `backend/app/main.py`: FastAPI application entry point.
- `backend/app/api/`: HTTP routes.
- `backend/app/services/`: import and domain-service logic.
- `backend/app/models/`: SQLAlchemy models.
- `backend/app/core/`: database configuration.
- `data/raw/`: source transaction reports; treat as immutable input.
- `aml.db`: local SQLite database generated/used by the backend.
- `notebooks/`: exploratory analysis.
- `tests/`: automated tests (currently empty).

## Development guidelines

- Preserve the current API behavior unless a change explicitly calls for an
  intentional breaking change.
- Keep database access in `core` and data-import/business logic in `services`;
  route modules should be thin.
- Validate uploaded files and clean up temporary upload files when implementing
  import changes.
- Use explicit data types and handle malformed values and dates defensively.
- Never commit credentials, virtual environments, generated caches, or raw
  production-sensitive transaction data.

## Verification

- Add or update tests in `tests/` with behavioral changes.
- Run the relevant test suite and report any dependency or environment blockers.
- Confirm schema-affecting changes against SQLite before considering work done.

## Current constraints

- The project has no Git repository metadata or dependency manifest yet.
- The backend expects pipe-delimited transaction-report CSV input with two
  leading report-metadata rows, as implemented in `transaction_service.py`.
