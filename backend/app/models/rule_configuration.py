from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint

from backend.app.core.database import Base


class RuleConfiguration(Base):
    __tablename__ = "rule_configurations"
    __table_args__ = (
        UniqueConstraint("rule_code", name="uq_rule_configuration_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    category = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
    priority = Column(Integer, nullable=False)
    parameters = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
