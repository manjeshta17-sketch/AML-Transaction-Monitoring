from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.transaction import Transaction
from backend.app.schemas.dashboard import (
    AlertMetrics,
    CaseMetrics,
    DashboardDistribution,
    DashboardSummary,
    RuleAlertCount,
    TransactionMetrics,
    TrendPoint,
)
from backend.app.services.rule_configuration_service import RuleConfigurationService


class DashboardService:
    """Read-only database aggregations for dashboard consumers."""

    RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}

    @classmethod
    def resolve_range(
        cls,
        time_range: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        reference_time: datetime | None = None,
    ) -> tuple[datetime | None, datetime | None]:
        if time_range is not None and time_range not in cls.RANGES:
            raise ValueError("Unsupported time range.")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must not be after date_to.")
        if time_range and (date_from is not None or date_to is not None):
            raise ValueError("Use either time_range or custom dates, not both.")
        if date_from is not None or date_to is not None:
            return date_from, date_to
        if time_range is None:
            return None, None
        end = reference_time or datetime.now(timezone.utc)
        return end - cls.RANGES[time_range], end

    @staticmethod
    def _filtered(query, column, date_from, date_to):
        if date_from is not None:
            query = query.filter(column >= date_from)
        if date_to is not None:
            query = query.filter(column <= date_to)
        return query

    @classmethod
    def transaction_metrics(cls, db: Session, date_from, date_to) -> TransactionMetrics:
        query = cls._filtered(db.query(Transaction), Transaction.txn_date, date_from, date_to)
        total, amount = query.with_entities(
            func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0.0)
        ).one()
        rows = query.with_entities(Transaction.transaction_type, func.count(Transaction.id)).group_by(
            Transaction.transaction_type
        ).all()
        return TransactionMetrics(
            total_transactions=total,
            total_transaction_amount=float(amount or 0),
            transaction_types={str(key): count for key, count in rows if key is not None},
        )

    @classmethod
    def alert_metrics(cls, db: Session, date_from, date_to) -> AlertMetrics:
        query = cls._filtered(db.query(Alert), Alert.created_at, date_from, date_to)
        total = query.count()
        open_count = query.filter(Alert.status == "OPEN").count()
        closed_count = query.filter(Alert.status == "CLOSED").count()
        by_rule = query.with_entities(Alert.rule_code, func.count(Alert.id)).group_by(Alert.rule_code).all()
        by_priority = query.with_entities(Alert.priority, func.count(Alert.id)).group_by(Alert.priority).all()
        by_risk = query.with_entities(Alert.risk_level, func.count(Alert.id)).group_by(Alert.risk_level).all()
        return AlertMetrics(
            total_alerts=total,
            open_alerts=open_count,
            closed_alerts=closed_count,
            by_rule={key: count for key, count in by_rule},
            by_priority={str(key): count for key, count in by_priority},
            by_risk_level={key: count for key, count in by_risk},
        )

    @classmethod
    def case_metrics(cls, db: Session, date_from, date_to) -> CaseMetrics:
        query = cls._filtered(db.query(Case), Case.created_at, date_from, date_to)
        total = query.count()
        rows = query.with_entities(Case.status, func.count(Case.id)).group_by(Case.status).all()
        priorities = query.with_entities(Case.priority, func.count(Case.id)).group_by(Case.priority).all()
        assigned = query.filter(Case.assigned_to.isnot(None), Case.assigned_to != "").count()
        return CaseMetrics(
            total_cases=total,
            by_status={key: count for key, count in rows},
            by_priority={str(key): count for key, count in priorities},
            assigned_cases=assigned,
            unassigned_cases=total - assigned,
        )

    @classmethod
    def summary(
        cls, db: Session, time_range=None, date_from=None, date_to=None, reference_time=None
    ) -> DashboardSummary:
        start, end = cls.resolve_range(time_range, date_from, date_to, reference_time)
        transactions = cls.transaction_metrics(db, start, end)
        alerts = cls.alert_metrics(db, start, end)
        cases = cls.case_metrics(db, start, end)
        return DashboardSummary(
            time_range=time_range,
            date_from=start,
            date_to=end,
            transactions=transactions,
            alerts=alerts,
            cases=cases,
            high_priority_alerts=alerts.by_priority.get("1", 0),
            high_priority_cases=cases.by_priority.get("1", 0),
        )

    @classmethod
    def trend(cls, db: Session, entity: str, time_range, date_from=None, date_to=None, reference_time=None):
        start, end = cls.resolve_range(time_range, date_from, date_to, reference_time)
        if start is None or end is None:
            raise ValueError("A time_range or custom date range is required for trends.")
        hourly = time_range == "24h"
        model, column = (
            (Alert, Alert.created_at) if entity == "alerts" else (Transaction, Transaction.txn_date)
        )
        bucket_format = "%Y-%m-%d %H:00:00" if hourly else "%Y-%m-%d 00:00:00"
        bucket = func.strftime(bucket_format, column)
        query = cls._filtered(db.query(bucket.label("bucket"), func.count(model.id)), column, start, end)
        rows = query.group_by(bucket).order_by(bucket).all()
        return [TrendPoint(bucket=datetime.fromisoformat(value), count=count) for value, count in rows]

    @classmethod
    def top_rules(cls, db: Session, date_from=None, date_to=None, reference_time=None):
        query = cls._filtered(db.query(Alert), Alert.created_at, date_from, date_to)
        rows = query.with_entities(Alert.rule_code, func.count(Alert.id)).group_by(
            Alert.rule_code
        ).order_by(func.count(Alert.id).desc()).all()
        names = {
            rule.rule_code: rule.name
            for rule in RuleConfigurationService.load_rules(db)
        }
        return [
            RuleAlertCount(rule_code=code, rule_name=names.get(code, code), alert_count=count)
            for code, count in rows
        ]
