from datetime import datetime

from pydantic import BaseModel


class CountItem(BaseModel):
    key: str
    count: int


class TransactionMetrics(BaseModel):
    total_transactions: int
    total_transaction_amount: float
    transaction_types: dict[str, int]


class AlertMetrics(BaseModel):
    total_alerts: int
    open_alerts: int
    closed_alerts: int
    by_rule: dict[str, int]
    by_priority: dict[str, int]
    by_risk_level: dict[str, int]


class CaseMetrics(BaseModel):
    total_cases: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    assigned_cases: int
    unassigned_cases: int


class DashboardSummary(BaseModel):
    time_range: str | None
    date_from: datetime | None
    date_to: datetime | None
    transactions: TransactionMetrics
    alerts: AlertMetrics
    cases: CaseMetrics
    high_priority_alerts: int
    high_priority_cases: int


class TrendPoint(BaseModel):
    bucket: datetime
    count: int


class RuleAlertCount(BaseModel):
    rule_code: str
    rule_name: str
    alert_count: int


class DashboardDistribution(BaseModel):
    alerts_by_risk_level: dict[str, int]
    alerts_by_priority: dict[str, int]
    cases_by_priority: dict[str, int]
