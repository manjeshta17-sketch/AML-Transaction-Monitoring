import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import (
    Base,
    SessionLocal,
    engine,
    ensure_alert_columns,
    ensure_transaction_import_columns,
    ensure_transaction_search_indexes,
    ensure_transaction_rule_columns,
)
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.case_comment import CaseComment
from backend.app.models.transaction import Transaction
from backend.app.models.transaction_import import TransactionImport
from backend.app.models.rule_configuration import RuleConfiguration
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.models.llm_assistance import AlertLLMAssistance
from backend.app.api.alerts import router as alert_router
from backend.app.api.cases import router as case_router
from backend.app.api.monitoring import router as monitoring_router
from backend.app.api.transactions import router as transaction_router
from backend.app.api.rules import router as rules_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.services.rule_configuration_service import RuleConfigurationService

Base.metadata.create_all(bind=engine)
ensure_transaction_rule_columns()
ensure_transaction_import_columns()
ensure_alert_columns()
ensure_transaction_search_indexes()
with SessionLocal() as startup_db:
    RuleConfigurationService.initialize(startup_db)


app = FastAPI(
    title="AML Transaction Monitoring System",
    description="Transaction monitoring and AML alert management API",
    version="1.0.0",
    openapi_tags=[
        {"name": "System", "description": "Service availability and metadata."},
        {"name": "Transactions", "description": "Transaction import, search, and details."},
        {"name": "Rules", "description": "Persisted AML rule configuration."},
        {"name": "Alerts", "description": "Alert search, workflow, and case creation."},
        {"name": "Cases", "description": "Investigation case workflow and comments."},
        {"name": "Dashboard", "description": "Read-only monitoring aggregates and trends."},
        {"name": "Monitoring", "description": "Rule evaluation and alert generation."},
    ],
)

logger = logging.getLogger(__name__)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
    }.get(exc.status_code, "HTTP_ERROR")
    detail = (
        exc.detail
        if isinstance(exc.detail, list)
        else [exc.detail]
        if isinstance(exc.detail, dict)
        else []
    )
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "details": detail}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database constraint conflict on %s", request.url.path)
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "CONFLICT",
                "message": "The requested operation conflicts with existing data.",
                "details": [],
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected API error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
                "details": [],
            }
        },
    )

app.include_router(transaction_router)
app.include_router(alert_router)
app.include_router(case_router)
app.include_router(monitoring_router)
app.include_router(rules_router)
app.include_router(dashboard_router)

@app.get(
    "/",
    tags=["System"],
    summary="Get API status",
    description="Returns a basic service availability message.",
)
def root():
    return {
        "message": "AML Transaction Monitoring API is running"
    }


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    description="Returns the current API health status.",
)
def health_check():
    return {
        "status": "healthy"
    }
