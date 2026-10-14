from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, asc, cast, desc, or_
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.models.ai_enrichment import TransactionAIEnrichment
from backend.app.schemas.alert import (
    AlertAssignmentUpdate,
    AlertDetail,
    AlertListResponse,
    AlertPriorityUpdate,
    AlertRead,
    AlertStatusUpdate,
)
from backend.app.schemas.case import CaseRead
from backend.app.services.case_service import CaseService
from backend.app.schemas.errors import ErrorResponse
from backend.app.schemas.llm_assistance import LLMAssistanceRead
from backend.app.services.llm_service import generate_assistance


router = APIRouter(prefix="/alerts", tags=["Alerts"])
ALERT_STATUSES = {"OPEN", "IN_PROGRESS", "CLOSED"}
SORT_FIELDS = {
    "id": Alert.id,
    "created_at": Alert.created_at,
    "updated_at": Alert.updated_at,
    "priority": Alert.priority,
    "status": Alert.status,
    "rule_code": Alert.rule_code,
}


def _alert_query(
    db: Session,
    status: str | None = None,
    rule_code: str | None = None,
    priority: int | None = None,
    assigned_to: str | None = None,
    transaction_id: int | None = None,
    customer_id: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    query = db.query(Alert)
    if status is not None:
        if status not in ALERT_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid alert status")
        query = query.filter(Alert.status == status)
    if rule_code is not None:
        query = query.filter(Alert.rule_code == rule_code)
    if priority is not None:
        if priority not in {1, 2, 3, 4}:
            raise HTTPException(status_code=422, detail="Invalid alert priority")
        query = query.filter(Alert.priority == priority)
    if assigned_to is not None:
        query = query.filter(Alert.assigned_to == assigned_to)
    if transaction_id is not None:
        query = query.filter(Alert.transaction_id == transaction_id)
    if customer_id is not None:
        query = query.filter(Alert.customer_id == customer_id)
    if date_from is not None:
        query = query.filter(Alert.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Alert.created_at <= date_to)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Alert.alert_code.ilike(term),
                Alert.rule_code.ilike(term),
                Alert.customer_id.ilike(term),
                cast(Alert.transaction_id, String).ilike(term),
            )
        )
    return query


def list_alerts(db: Session = Depends(get_db)):
    """Backward-compatible service-style listing used by existing callers."""
    return db.query(Alert).order_by(Alert.id).all()


@router.get(
    "",
    response_model=AlertListResponse,
    summary="Search and list alerts",
    description="Returns database-filtered, sorted, and paginated AML alerts.",
    responses={422: {"model": ErrorResponse, "description": "Invalid alert filters, pagination, or sorting."}},
)
def list_alerts_endpoint(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    rule_code: str | None = None,
    priority: int | None = None,
    assigned_to: str | None = None,
    transaction_id: int | None = None,
    customer_id: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
    db: Session = Depends(get_db),
):
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be at least 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 100")
    if transaction_id is not None and transaction_id < 1:
        raise HTTPException(status_code=422, detail="transaction_id must be positive")
    if sort_by not in SORT_FIELDS:
        raise HTTPException(status_code=422, detail="Invalid sort field")
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort order")
    query = _alert_query(
        db, status, rule_code, priority, assigned_to, transaction_id,
        customer_id, search, date_from, date_to,
    )
    total = query.count()
    order_column = SORT_FIELDS[sort_by]
    query = query.order_by((asc if sort_order == "asc" else desc)(order_column), Alert.id)
    alerts = query.offset((page - 1) * page_size).limit(page_size).all()
    return AlertListResponse(
        alerts=alerts,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.post(
    "/{alert_id}/ai-assistance",
    response_model=LLMAssistanceRead,
    summary="Generate grounded analyst assistance",
    description="Generates optional, validated analyst assistance without changing alert workflow state.",
    responses={404: {"model": ErrorResponse, "description": "Alert was not found."}},
)
def generate_alert_ai_assistance(alert_id: int, db: Session = Depends(get_db)):
    alert = _get_alert_or_404(alert_id, db)
    transaction = db.get(Transaction, alert.transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Alert transaction not found")
    enrichment = (
        db.query(TransactionAIEnrichment)
        .filter(TransactionAIEnrichment.transaction_id == transaction.id)
        .one_or_none()
    )
    return generate_assistance(alert, transaction, enrichment, db)


@router.get(
    "/{alert_id}",
    response_model=AlertDetail,
    summary="Get alert details",
    description="Returns an alert and a bounded summary of its source transaction.",
    responses={
        404: {"model": ErrorResponse, "description": "Alert was not found."},
        422: {"model": ErrorResponse, "description": "The alert identifier is invalid."},
    },
)
def get_alert(alert_id: int | str, db: Session = Depends(get_db)):
    alert_text = str(alert_id)
    alert = db.get(Alert, int(alert_text)) if alert_text.isdigit() else (
        db.query(Alert).filter(Alert.alert_code == alert_id).one_or_none()
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    transaction = db.get(Transaction, alert.transaction_id)
    return AlertDetail.model_validate({**alert.__dict__, "transaction": transaction})


def _get_alert_or_404(alert_id: int, db: Session) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch(
    "/{alert_id}/status",
    response_model=AlertRead,
    summary="Update alert status",
    responses={
        404: {"model": ErrorResponse, "description": "Alert was not found."},
        422: {"model": ErrorResponse, "description": "Status is invalid."},
    },
)
def update_alert_status(alert_id: int, update: AlertStatusUpdate, db: Session = Depends(get_db)):
    if update.status not in ALERT_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid alert status")
    alert = _get_alert_or_404(alert_id, db)
    alert.status = update.status
    db.commit()
    db.refresh(alert)
    return alert


@router.patch(
    "/{alert_id}/priority",
    response_model=AlertRead,
    summary="Update alert priority",
    responses={
        404: {"model": ErrorResponse, "description": "Alert was not found."},
        422: {"model": ErrorResponse, "description": "Priority must be between 1 and 4."},
    },
)
def update_alert_priority(alert_id: int, update: AlertPriorityUpdate, db: Session = Depends(get_db)):
    alert = _get_alert_or_404(alert_id, db)
    alert.priority = update.priority
    db.commit()
    db.refresh(alert)
    return alert


@router.patch(
    "/{alert_id}/assignment",
    response_model=AlertRead,
    summary="Assign an alert",
    description="Assigns an alert to an analyst or clears its assignment with null.",
    responses={404: {"model": ErrorResponse, "description": "Alert was not found."}},
)
def update_alert_assignment(
    alert_id: int, update: AlertAssignmentUpdate, db: Session = Depends(get_db)
):
    alert = _get_alert_or_404(alert_id, db)
    alert.assigned_to = update.assigned_to.strip() if update.assigned_to else None
    db.commit()
    db.refresh(alert)
    return alert


@router.post(
    "/{alert_id}/case",
    response_model=CaseRead,
    status_code=201,
    summary="Create a case from an alert",
    description="Creates the single case associated with an alert. Existing cases are not duplicated.",
    responses={
        404: {"model": ErrorResponse, "description": "Alert was not found."},
        409: {"model": ErrorResponse, "description": "A case already exists for this alert."},
    },
)
def create_case_from_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = _get_alert_or_404(alert_id, db)
    case = CaseService.create_case_from_alert(alert, db)
    if case is None:
        raise HTTPException(status_code=409, detail="A case already exists for this alert")
    db.commit()
    db.refresh(case)
    return case
