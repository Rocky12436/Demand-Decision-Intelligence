from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Float, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False, default="upload")  # 'seed' or 'upload'
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    row_count = Column(Integer, nullable=False, default=0)
    date_min = Column(Date, nullable=True)
    date_max = Column(Date, nullable=True)

    user = relationship("User", backref="datasets")
    sales_transactions = relationship("SalesTransaction", back_populates="dataset", cascade="all, delete-orphan")
    daily_demands = relationship("DailyProductDemand", back_populates="dataset", cascade="all, delete-orphan")
    forecast_runs = relationship("ForecastRun", back_populates="dataset", cascade="all, delete-orphan")
    sku_mappings = relationship("SkuMapping", back_populates="dataset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_datasets_user_active", "user_id", "is_active"),
    )


class SkuMapping(Base):
    __tablename__ = "sku_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    external_sku = Column(String(100), nullable=False, index=True)
    internal_product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=True)
    confidence = Column(Float, nullable=True)
    mapping_method = Column(String(50), nullable=False)  # 'exact', 'fuzzy', 'manual'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dataset = relationship("Dataset", back_populates="sku_mappings")
    product = relationship("Product", backref="sku_mappings")

    __table_args__ = (
        Index("idx_sku_mappings_external_sku", "external_sku"),
        Index("idx_sku_mappings_dataset_sku", "dataset_id", "external_sku"),
    )
