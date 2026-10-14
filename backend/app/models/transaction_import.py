from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from backend.app.core.database import Base


class TransactionImport(Base):
    __tablename__ = "transaction_imports"

    id = Column(Integer, primary_key=True, index=True)
    source_filename = Column(String, nullable=True)
    status = Column(String, nullable=False, default="COMPLETED")
    rows_processed = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
