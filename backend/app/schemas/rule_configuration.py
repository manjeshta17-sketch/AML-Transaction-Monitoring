from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleConfigurationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = Field(default=None, description="Whether the rule is evaluated.")
    priority: int | None = Field(default=None, ge=1, description="Positive rule priority.")
    risk_level: str | None = Field(
        default=None, description="Risk level: low, medium, high, or critical.",
        examples=["high"],
    )
    parameters: dict[str, Any] | None = Field(
        default=None, description="Rule-specific JSON parameters validated by the service.",
        examples=[{"transaction_type": "LOAD", "amount_threshold": 7000}],
    )


class RuleConfigurationRead(BaseModel):
    id: int
    rule_code: str
    name: str
    description: str
    enabled: bool
    category: str
    risk_level: str
    priority: int
    parameters: dict[str, Any]
    created_at: Any
    updated_at: Any

    model_config = ConfigDict(from_attributes=True)
