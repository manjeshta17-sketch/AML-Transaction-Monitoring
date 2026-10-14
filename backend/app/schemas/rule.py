"""Rule configuration and evaluation result schemas.

Rules are deliberately independent of alert persistence. They can later be
loaded from a database or configuration source without changing the engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class RuleDefinition:
    rule_code: str
    name: str
    description: str
    category: str
    risk_level: str
    priority: int
    enabled: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleTriggerResult:
    """A rule match for one transaction; this is not an alert record."""

    rule_code: str
    rule_name: str
    category: str
    risk_level: str
    priority: int
    transaction_id: int | None
    ext_txn_id: str | None
    transaction_type: str | None
    amount: float | None
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class InsufficientHistoryResult:
    rule_code: str
    entity_field: str
    entity_value: str | None
    evaluation_month: datetime
    required_months: int
    available_months: int
    reason: str


@dataclass(frozen=True)
class DataInsufficientResult:
    rule_code: str
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RuleEvaluationOutcome:
    triggers: list[RuleTriggerResult]
    insufficient_history: list[InsufficientHistoryResult]
    data_insufficient: list[DataInsufficientResult] = field(default_factory=list)
