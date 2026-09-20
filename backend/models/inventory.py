from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base

class InventoryState(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    opening_stock = Column(Float, nullable=False, default=0.0)
    stock_received = Column(Float, nullable=False, default=0.0)
    sales_quantity = Column(Float, nullable=False, default=0.0)
    closing_stock = Column(Float, nullable=False, default=0.0)
    is_simulated = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="inventory_states")

    __table_args__ = (
        UniqueConstraint("dataset_id", "product_id", "city_name", "snapshot_date", name="uq_inventory_dataset_product_city_date"),
        Index("idx_inventory_product_date", "product_id", "snapshot_date"),
        Index("idx_inventory_dataset_id", "dataset_id"),
    )

class InventoryRecommendation(Base):
    __tablename__ = "inventory_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    calculation_date = Column(Date, nullable=False, index=True)
    current_stock = Column(Float, nullable=False, default=0.0)
    avg_daily_demand = Column(Float, nullable=False, default=0.0)
    lead_time_days = Column(Integer, nullable=False, default=3)
    safety_stock = Column(Float, nullable=False, default=0.0)
    reorder_point = Column(Float, nullable=False, default=0.0)
    recommended_order_qty = Column(Float, nullable=False, default=0.0)
    risk_status = Column(String(50), nullable=False, default="OPTIMAL", index=True)
    priority = Column(String(20), nullable=False, default="MEDIUM")
    is_stale = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="inventory_recommendations")

    __table_args__ = (
        Index("idx_inv_rec_product_date", "product_id", "calculation_date"),
        Index("idx_inv_rec_risk", "risk_status", "priority"),
        Index("idx_inv_rec_dataset_id", "dataset_id"),
    )
