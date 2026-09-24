"""
SQLAlchemy models for Weekly Executive Narrative Digests (Prompt 5.6)
Project: Demand-Decision-Intelligence
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class WeeklyDigest(Base):
    """
    Auto-generated weekly executive narrative digest with structured numbers appendix.
    """
    __tablename__ = "weekly_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    week_end_date = Column(Date, nullable=False, index=True)
    headline = Column(String(255), nullable=False)
    narrative_prose = Column(Text, nullable=False)
    structured_numbers = Column(JSON, nullable=False)
    delivered_email = Column(String(255), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", backref="weekly_digests")

    __table_args__ = (
        Index("idx_digest_dataset_dates", "dataset_id", "week_start_date", "week_end_date"),
    )
