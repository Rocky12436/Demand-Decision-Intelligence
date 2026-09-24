"""
backend/models/recommendation.py
--------------------------------
SQLAlchemy models for Recommendation lifecycle, append-only event audit trail,
and Forecast Accuracy accountability (Prompt 4.2).
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class ActionRecommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    type = Column(
        String(50),
        nullable=False,
        default="reorder",
        index=True
    )  # reorder, bulk_purchase, trim_order, transfer, markdown, delist
    status = Column(
        String(50),
        nullable=False,
        default="NEW",
        index=True
    )  # NEW, ACKNOWLEDGED, APPROVED, PO_ISSUED, RECEIVED, CLOSED, REJECTED, SNOOZED
    recommended_qty = Column(Float, nullable=False, default=0.0)
    rationale_json = Column(JSON, nullable=True)
    expected_value_impact = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    actioned_at = Column(DateTime(timezone=True), nullable=True)
    actioned_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    product = relationship("Product")
    events = relationship("RecommendationEvent", back_populates="recommendation", cascade="all, delete-orphan")


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(50), nullable=False)
    to_status = Column(String(50), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    recommendation = relationship("ActionRecommendation", back_populates="events")


class ForecastAccuracy(Base):
    __tablename__ = "forecast_accuracy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    horizon_date = Column(Date, nullable=False, index=True)
    predicted_demand = Column(Float, nullable=False)
    actual_demand = Column(Float, nullable=False)
    abs_error = Column(Float, nullable=False)
    ape = Column(Float, nullable=False)  # Absolute percentage error
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")
