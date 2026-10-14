from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.core.database import Base


class TransactionAIEnrichment(Base):
    __tablename__ = "transaction_ai_enrichments"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, unique=True, index=True)
    model_version = Column(String, nullable=False)
    feature_pipeline_version = Column(String, nullable=False)
    anomaly_score = Column(Float, nullable=True)
    anomaly_flag = Column(Boolean, nullable=True)
    history_sufficient = Column(Boolean, nullable=False)
    enrichment_status = Column(String, nullable=False)
    evidence_json = Column(Text, nullable=True)
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    transaction = relationship("Transaction")
