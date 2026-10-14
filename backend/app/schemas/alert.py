from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_code: str
    rule_code: str
    rule_name: str
    description: str | None
    transaction_id: int
    customer_id: str | None
    card_number: str | None
    amount: float | None
    risk_level: str
    priority: int
    status: str
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    alerts: list[AlertRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class AlertStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        min_length=1,
        description="Alert workflow status: OPEN, IN_PROGRESS, or CLOSED.",
        examples=["CLOSED"],
    )

    @field_validator("status")
    @classmethod
    def reject_blank_status(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("status must not be blank.")
        return value


class AlertPriorityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(
        ge=1, le=4, description="Alert priority from 1 (highest) to 4 (lowest).",
        examples=[1],
    )


class AlertAssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str | None = Field(
        default=None, max_length=255,
        description="Analyst identifier; null clears the assignment.",
        examples=["analyst-1"],
    )

    @field_validator("assigned_to")
    @classmethod
    def reject_blank_assignment(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("assigned_to must not be blank.")
        return value


class AlertDetail(AlertRead):
    transaction: "TransactionSummary | None" = None


class TransactionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ext_txn_id: str | None
    transaction_type: str | None
    amount: float | None
    txn_date: datetime | None
    customer_id: str | None
    card_number: str | None
