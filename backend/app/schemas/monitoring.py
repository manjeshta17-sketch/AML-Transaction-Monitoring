from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InsufficientHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_code: str
    entity_field: str
    entity_value: str | None
    evaluation_month: datetime
    required_months: int
    available_months: int
    reason: str


class DataInsufficientItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_code: str
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    reason: str


class MonitoringRunResponse(BaseModel):
    transactions_evaluated: int = Field(description="Transactions evaluated during the run.")
    alerts_generated: int = Field(description="New alerts persisted during the run.")
    alerts_by_rule: dict[str, int] = Field(description="New alert counts grouped by rule code.")
    insufficient_history: list[InsufficientHistoryItem] = Field(
        description="Historical evaluations that could not produce alerts."
    )
    data_insufficient: list[DataInsufficientItem] = Field(
        description="Rule evaluations skipped because required data was unavailable."
    )


class RuleCoverageItem(BaseModel):
    rule_code: str
    rule_name: str
    category: str
    has_sufficient_data: bool
    reason: str | None = None
    alerts_generated: int = 0
