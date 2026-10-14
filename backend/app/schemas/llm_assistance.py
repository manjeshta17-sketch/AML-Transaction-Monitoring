from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LLMAssistanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    provider: str
    model: str | None
    prompt_version: str
    response_status: str
    validated: bool
    generated_response: str | None
    generated_at: datetime
    latency_ms: int | None
