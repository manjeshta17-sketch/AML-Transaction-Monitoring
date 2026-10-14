from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint

from backend.app.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("transaction_id", "rule_code", name="uq_alert_transaction_rule"),
    )

    id = Column(Integer, primary_key=True, index=True)
    alert_code = Column(String, nullable=False, unique=True, index=True)
    rule_code = Column(String, nullable=False, index=True)
    rule_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    customer_id = Column(String, nullable=True, index=True)
    card_number = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    risk_level = Column(String, nullable=False)
    priority = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="OPEN")
    assigned_to = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
