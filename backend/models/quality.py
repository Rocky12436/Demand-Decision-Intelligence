"""
Data Quality Scorecard Models (Prompt 5.9)
Project: Demand-Decision-Intelligence

Tracks upload and dataset-level data quality metrics across 10 dimensions:
- Completeness
- Date continuity / gaps
- Value validity / negatives
- Uniqueness / collisions
- Outlier sanity
- SKU mapping
- Type coercion
- Zero-inflation
- History depth
- Freshness
Rolls up to a single 0-100 composite score that gates complex model selection.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from backend.db.session import Base


class DataQualityScorecard(Base):
    __tablename__ = "data_quality_scorecards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_job_id = Column(Integer, ForeignKey("upload_jobs.id", ondelete="SET NULL"), nullable=True, index=True)

    composite_score = Column(Float, nullable=False, default=100.0)  # 0 to 100
    quality_gate_passed = Column(Boolean, nullable=False, default=True)  # True if score >= 50

    # 10 Component Scores (0 to max weights)
    completeness_score = Column(Float, nullable=False, default=20.0)  # max 20
    date_gap_score = Column(Float, nullable=False, default=15.0)      # max 15
    value_validity_score = Column(Float, nullable=False, default=15.0)# max 15
    uniqueness_score = Column(Float, nullable=False, default=10.0)    # max 10
    outlier_score = Column(Float, nullable=False, default=10.0)       # max 10
    sku_mapping_score = Column(Float, nullable=False, default=10.0)   # max 10
    type_coercion_score = Column(Float, nullable=False, default=5.0)  # max 5
    zero_inflation_score = Column(Float, nullable=False, default=5.0) # max 5
    history_depth_score = Column(Float, nullable=False, default=5.0)  # max 5
    freshness_score = Column(Float, nullable=False, default=5.0)      # max 5

    # Structured Audit Payload
    metrics_breakdown = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_dqs_dataset_created", "dataset_id", "created_at"),
    )
