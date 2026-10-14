from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from backend.app.core.database import Base


class AlertLLMAssistance(Base):
    __tablename__ = "alert_llm_assistance"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=True)
    prompt_version = Column(String, nullable=False)
    response_status = Column(String, nullable=False)
    validated = Column(Boolean, nullable=False, default=False)
    generated_response = Column(Text, nullable=True)
    generated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    latency_ms = Column(Integer, nullable=True)
