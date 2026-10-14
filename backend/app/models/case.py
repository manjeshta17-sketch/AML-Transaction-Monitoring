from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from backend.app.core.database import Base


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("alert_id", name="uq_case_alert"),)

    id = Column(Integer, primary_key=True, index=True)
    case_code = Column(String, nullable=False, unique=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="OPEN", index=True)
    priority = Column(Integer, nullable=False)
    assigned_to = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
