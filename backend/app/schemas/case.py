from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_code: str
    alert_id: int
    status: str
    priority: int
    assigned_to: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class CaseListResponse(BaseModel):
    cases: list[CaseRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class CaseAlertSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_code: str
    rule_code: str
    rule_name: str
    description: str | None
    transaction_id: int
    customer_id: str | None
    amount: float | None
    priority: int
    status: str


class CaseTransactionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ext_txn_id: str | None
    transaction_type: str | None
    amount: float | None
    txn_date: datetime | None
    customer_id: str | None
    card_number: str | None


class CaseDetail(CaseRead):
    alert: CaseAlertSummary | None = None
    transaction: CaseTransactionSummary | None = None
    comments: list["CaseCommentRead"] = []


class CaseStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        description="Case workflow status: OPEN, IN_PROGRESS, or CLOSED.",
        examples=["IN_PROGRESS"],
    )


class CasePriorityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(
        ge=1, le=4, description="Case priority from 1 (highest) to 4 (lowest).",
        examples=[1],
    )


class CaseAssignmentUpdate(BaseModel):
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


class CaseCommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(
        min_length=1, max_length=10000,
        description="Investigation note.",
        examples=["Reviewed transaction context."],
    )
    created_by: str = Field(
        min_length=1, max_length=255,
        description="Analyst or service creating the comment.",
        examples=["analyst-1"],
    )

    @field_validator("comment", "created_by")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class CaseCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    comment: str
    created_by: str
    created_at: datetime
