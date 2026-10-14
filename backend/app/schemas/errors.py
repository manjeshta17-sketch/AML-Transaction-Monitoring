from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable application error code.")
    message: str = Field(description="Safe, human-readable error message.")
    details: list[Any] = Field(
        default_factory=list,
        description="Additional validation or conflict details.",
    )


class ErrorResponse(BaseModel):
    error: ErrorBody

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "Transaction not found.",
                        "details": [],
                    }
                }
            ]
        }
    )
