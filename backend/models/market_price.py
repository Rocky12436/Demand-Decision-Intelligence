from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class CommodityMapping(Base):
    __tablename__ = "commodity_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    commodity_code = Column(String(50), nullable=False, index=True)
    commodity_name = Column(String(150), nullable=False)
    market_name = Column(String(100), nullable=False, default="ALL")
    source_unit = Column(String(50), nullable=False, default="Rs/quintal")
    conversion_factor_to_internal = Column(Float, nullable=False, default=0.01)  # e.g., 1 quintal = 100 kg -> 0.01
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", backref="commodity_mappings")

    __table_args__ = (
        Index("idx_cm_prod_comm", "product_id", "commodity_code"),
    )


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    commodity_code = Column(String(50), nullable=False, index=True)
    market_name = Column(String(100), nullable=False, index=True)
    observed_date = Column(Date, nullable=False, index=True)
    wholesale_price = Column(Float, nullable=True)
    retail_price = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    source = Column(String(100), nullable=False, default="fcainfoweb.nic.in")
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    is_interpolated = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_po_comm_obs_date", "commodity_code", "observed_date"),
        Index("idx_po_market_date", "market_name", "observed_date"),
    )


class CategoryPriceThreshold(Base):
    __tablename__ = "category_price_thresholds"

    category_name = Column(String(100), primary_key=True)
    bulk_threshold_pct = Column(Float, nullable=False, default=8.0)
    trim_threshold_pct = Column(Float, nullable=False, default=-8.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
