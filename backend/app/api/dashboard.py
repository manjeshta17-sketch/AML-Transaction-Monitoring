from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.schemas.dashboard import DashboardDistribution, DashboardSummary, RuleAlertCount, TrendPoint
from backend.app.services.dashboard_service import DashboardService
from backend.app.schemas.errors import ErrorResponse


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _range_args(time_range, date_from, date_to):
    try:
        return DashboardService.resolve_range(time_range, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get dashboard summary",
    description="Returns aggregated transaction, alert, and case metrics for all data or a selected time range.",
    responses={422: {"model": ErrorResponse, "description": "Invalid time range or custom date range."}},
)
def dashboard_summary(
    time_range: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    _range_args(time_range, date_from, date_to)
    return DashboardService.summary(db, time_range, date_from, date_to)


@router.get(
    "/alerts/trend",
    response_model=list[TrendPoint],
    summary="Get alert trend",
    description="Returns alert counts grouped hourly for 24h or daily for longer ranges.",
    responses={422: {"model": ErrorResponse, "description": "A time range or valid custom range is required."}},
)
def alert_trend(
    time_range: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    try:
        return DashboardService.trend(db, "alerts", time_range, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/transactions/trend",
    response_model=list[TrendPoint],
    summary="Get transaction trend",
    description="Returns transaction counts grouped hourly for 24h or daily for longer ranges.",
    responses={422: {"model": ErrorResponse, "description": "A time range or valid custom range is required."}},
)
def transaction_trend(
    time_range: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    try:
        return DashboardService.trend(db, "transactions", time_range, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/rules/top",
    response_model=list[RuleAlertCount],
    summary="Get top alert-generating rules",
    description="Returns rules ordered by alert count for the optional custom date range.",
    responses={422: {"model": ErrorResponse, "description": "Invalid custom date range."}},
)
def top_rules(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    _range_args(None, date_from, date_to)
    return DashboardService.top_rules(db, date_from, date_to)


@router.get(
    "/distributions",
    response_model=DashboardDistribution,
    summary="Get dashboard distributions",
    description="Returns alert risk/priority and case priority distributions.",
)
def distributions(db: Session = Depends(get_db)):
    summary = DashboardService.summary(db)
    return DashboardDistribution(
        alerts_by_risk_level=summary.alerts.by_risk_level,
        alerts_by_priority=summary.alerts.by_priority,
        cases_by_priority=summary.cases.by_priority,
    )
