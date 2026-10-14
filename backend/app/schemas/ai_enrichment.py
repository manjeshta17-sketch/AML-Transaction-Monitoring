from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AIEnrichmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    model_version: str
    feature_pipeline_version: str
    anomaly_score: float | None
    anomaly_flag: bool | None
    history_sufficient: bool
    enrichment_status: str
    generated_at: datetime
