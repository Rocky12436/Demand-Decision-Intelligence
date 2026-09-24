"""
backend/models/classification.py
---------------------------------
SQLAlchemy models for ABC-XYZ segmentation and configurable cell policies (Prompt 4.7)
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class AbcXyzPolicy(Base):
    """
    Configurable policy matrix for the 9 ABC-XYZ cells.
    Allows tuning target service level, review frequency, safety stock rules,
    and automation per cell without hardcoding if-statements.
    """
    __tablename__ = "abc_xyz_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cell = Column(String(2), unique=True, nullable=False, index=True)  # AX, AY, AZ, BX, BY, BZ, CX, CY, CZ
    abc_class = Column(String(1), nullable=False)  # A, B, C
    xyz_class = Column(String(1), nullable=False)  # X, Y, Z
    review_strategy = Column(String(50), nullable=False, default="CONTINUOUS")  # CONTINUOUS, PERIODIC, MIN_MAX, MAKE_TO_ORDER
    target_service_level = Column(Float, nullable=False, default=0.95)  # e.g. 0.98, 0.95, 0.90, 0.0
    safety_stock_policy = Column(String(100), nullable=False, default="STANDARD_KINGS")  # KINGS_HIGH_BUFFER, STANDARD_KINGS, MINIMAL, ZERO_STOCK
    reorder_automation = Column(String(50), nullable=False, default="AUTOMATED")  # AUTOMATED, MANUAL_APPROVAL, HUMAN_REVIEW, DO_NOT_STOCK
    review_frequency_days = Column(Integer, nullable=False, default=1)  # 1 (daily), 7 (weekly), 14 (bi-weekly), 30 (monthly)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProductClassification(Base):
    """
    Audit snapshot of SKU ABC-XYZ classification with underlying statistics.
    """
    __tablename__ = "product_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    abc_class = Column(String(1), nullable=False, index=True)  # A, B, C
    xyz_class = Column(String(1), nullable=False, index=True)  # X, Y, Z
    cell = Column(String(2), nullable=False, index=True)  # AX, AY, etc.
    annual_consumption_value = Column(Float, nullable=False, default=0.0)
    value_share_cumulative = Column(Float, nullable=True, default=0.0)
    cv2 = Column(Float, nullable=False, default=0.0)  # (sigma_d / mean_d)^2
    mean_daily_demand = Column(Float, nullable=False, default=0.0)
    std_daily_demand = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", backref="classifications")
    dataset = relationship("Dataset", backref="product_classifications")

    __table_args__ = (
        Index("idx_prod_class_dataset_cell", "dataset_id", "cell"),
        Index("idx_prod_class_dataset_product", "dataset_id", "product_id"),
    )
