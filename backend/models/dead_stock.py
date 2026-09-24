"""
backend/models/dead_stock.py
----------------------------
SQLAlchemy models for Dead Stock and Downward Actions (Prompt 4.8)
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Index, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class DeadStockRecord(Base):
    """
    Stores detected dead/excess stock records with financial liabilities
    and recommended downward clearance actions.
    """
    __tablename__ = "dead_stock_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    on_hand = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    selling_price = Column(Float, nullable=False, default=0.0)
    days_inactive = Column(Integer, nullable=False, default=0)
    days_of_cover = Column(Float, nullable=False, default=0.0)
    capital_tied_up = Column(Float, nullable=False, default=0.0)  # on_hand * unit_cost
    monthly_storage_cost = Column(Float, nullable=False, default=0.0)
    projected_obsolescence_date = Column(Date, nullable=True)

    # Downward Action Recommendation:
    # MARKDOWN, TRANSFER, BUNDLE, RETURN_TO_SUPPLIER, WRITE_OFF, DELIST
    recommended_action = Column(String(50), nullable=False, default="MARKDOWN", index=True)
    suggested_discount_pct = Column(Float, nullable=False, default=0.0)  # e.g. 0.20 for 20%
    elasticity_used = Column(Float, nullable=True, default=-1.5)
    is_assumption = Column(Boolean, nullable=False, default=True)
    projected_recovery_value = Column(Float, nullable=False, default=0.0)
    transfer_destination_city = Column(String(100), nullable=True)
    bundle_partner_product_id = Column(String(100), nullable=True)
    reasoning = Column(Text, nullable=True)

    # Status: PENDING, APPLIED, DISMISSED
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    action_notes = Column(Text, nullable=True)
    action_applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", backref="dead_stock_records")
    dataset = relationship("Dataset", backref="dead_stock_records")

    __table_args__ = (
        Index("idx_dead_stock_dataset_status", "dataset_id", "status"),
        Index("idx_dead_stock_dataset_action", "dataset_id", "recommended_action"),
    )
