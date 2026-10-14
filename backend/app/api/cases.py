from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, asc, cast, desc, or_
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.case_comment import CaseComment
from backend.app.models.transaction import Transaction
from backend.app.schemas.case import (
    CaseAlertSummary,
    CaseAssignmentUpdate,
    CaseCommentCreate,
    CaseCommentRead,
    CaseDetail,
    CaseListResponse,
    CasePriorityUpdate,
    CaseRead,
    CaseStatusUpdate,
    CaseTransactionSummary,
)
from backend.app.services.case_service import CaseService
from backend.app.schemas.errors import ErrorResponse


router = APIRouter(prefix="/cases", tags=["Cases"])
CASE_STATUSES = {"OPEN", "IN_PROGRESS", "CLOSED"}
SORT_FIELDS = {
    "id": Case.id,
    "created_at": Case.created_at,
    "updated_at": Case.updated_at,
    "priority": Case.priority,
    "status": Case.status,
}


def _get_case_or_404(case_id: int, db: Session) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get(
    "",
    response_model=CaseListResponse,
    summary="Search and list cases",
    description="Returns database-filtered, sorted, and paginated investigation cases.",
    responses={422: {"model": ErrorResponse, "description": "Invalid case filters, pagination, or sorting."}},
)
def list_cases(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    priority: int | None = None,
    assigned_to: str | None = None,
    alert_id: int | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
    db: Session = Depends(get_db),
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid page or page_size")
    if priority is not None and priority not in {1, 2, 3, 4}:
        raise HTTPException(status_code=422, detail="Invalid case priority")
    if status is not None and status not in CASE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid case status")
    if sort_by not in SORT_FIELDS or sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort options")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if alert_id is not None and alert_id < 1:
        raise HTTPException(status_code=422, detail="Invalid alert_id")

    query = db.query(Case)
    if status is not None:
        query = query.filter(Case.status == status)
    if priority is not None:
        query = query.filter(Case.priority == priority)
    if assigned_to is not None:
        query = query.filter(Case.assigned_to == assigned_to)
    if alert_id is not None:
        query = query.filter(Case.alert_id == alert_id)
    if date_from is not None:
        query = query.filter(Case.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Case.created_at <= date_to)
    if search:
        term = f"%{search.strip()}%"
        query = query.join(Alert, Case.alert_id == Alert.id).join(
            Transaction, Alert.transaction_id == Transaction.id
        ).filter(
            or_(
                Case.case_code.ilike(term),
                cast(Case.id, String).ilike(term),
                cast(Case.alert_id, String).ilike(term),
                Alert.alert_code.ilike(term),
                Alert.rule_code.ilike(term),
                cast(Alert.transaction_id, String).ilike(term),
                Alert.customer_id.ilike(term),
            )
        )

    total = query.count()
    sort_column = SORT_FIELDS[sort_by]
    query = query.order_by((asc if sort_order == "asc" else desc)(sort_column), Case.id)
    cases = query.offset((page - 1) * page_size).limit(page_size).all()
    return CaseListResponse(
        cases=cases,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Get case details",
    description="Returns case workflow data with related alert, transaction, and comments.",
    responses={
        404: {"model": ErrorResponse, "description": "Case was not found."},
        422: {"model": ErrorResponse, "description": "The case identifier is invalid."},
    },
)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    alert = db.get(Alert, case.alert_id)
    transaction = db.get(Transaction, alert.transaction_id) if alert else None
    comments = db.query(CaseComment).filter(
        CaseComment.case_id == case.id
    ).order_by(CaseComment.id).all()
    return CaseDetail(
        id=case.id,
        case_code=case.case_code,
        alert_id=case.alert_id,
        status=case.status,
        priority=case.priority,
        assigned_to=case.assigned_to,
        created_at=case.created_at,
        updated_at=case.updated_at,
        closed_at=case.closed_at,
        alert=CaseAlertSummary.model_validate(alert) if alert else None,
        transaction=CaseTransactionSummary.model_validate(transaction) if transaction else None,
        comments=comments,
    )


@router.patch(
    "/{case_id}/status",
    response_model=CaseRead,
    summary="Update case status",
    description="Applies the supported case status transition.",
    responses={
        400: {"model": ErrorResponse, "description": "The requested status transition is not allowed."},
        404: {"model": ErrorResponse, "description": "Case was not found."},
    },
)
def update_case_status(case_id: int, status_update: CaseStatusUpdate, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    try:
        CaseService.update_status(case, status_update.status)
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    db.refresh(case)
    return case


@router.patch(
    "/{case_id}/priority",
    response_model=CaseRead,
    summary="Update case priority",
    responses={
        404: {"model": ErrorResponse, "description": "Case was not found."},
        422: {"model": ErrorResponse, "description": "Priority must be between 1 and 4."},
    },
)
def update_case_priority(case_id: int, update: CasePriorityUpdate, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    try:
        CaseService.update_priority(case, update.priority)
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    db.refresh(case)
    return case


@router.patch(
    "/{case_id}/assignment",
    response_model=CaseRead,
    summary="Assign a case",
    description="Assigns a case to an analyst or clears its assignment with null.",
    responses={404: {"model": ErrorResponse, "description": "Case was not found."}},
)
def update_case_assignment(case_id: int, update: CaseAssignmentUpdate, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    try:
        CaseService.update_assignment(case, update.assigned_to)
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    db.refresh(case)
    return case


@router.post(
    "/{case_id}/comments",
    response_model=CaseCommentRead,
    status_code=201,
    summary="Add a case comment",
    description="Adds an analyst investigation comment to a case.",
    responses={
        404: {"model": ErrorResponse, "description": "Case was not found."},
        422: {"model": ErrorResponse, "description": "Comment validation failed."},
    },
)
def add_case_comment(case_id: int, comment_data: CaseCommentCreate, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    try:
        comment = CaseService.add_comment(case, comment_data.comment, comment_data.created_by, db)
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    db.refresh(comment)
    return comment


@router.get(
    "/{case_id}/comments",
    response_model=list[CaseCommentRead],
    summary="List case comments",
    responses={404: {"model": ErrorResponse, "description": "Case was not found."}},
)
def list_case_comments(case_id: int, db: Session = Depends(get_db)):
    case = _get_case_or_404(case_id, db)
    return db.query(CaseComment).filter(
        CaseComment.case_id == case.id
    ).order_by(CaseComment.id).all()
