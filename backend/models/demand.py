from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base

class DailyProductDemand(Base):
    __tablename__ = "daily_product_demand"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_job_id = Column(Integer, ForeignKey("upload_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    date_ = Column(Date, nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    total_quantity = Column(Float, nullable=False, default=0.0)
    total_sales_value = Column(Float, nullable=False, default=0.0)
    total_discount_value = Column(Float, nullable=False, default=0.0)
    avg_unit_price = Column(Float, nullable=True)
    order_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="daily_demands")
    dataset = relationship("Dataset", back_populates="daily_demands")
    upload_job = relationship("UploadJob", backref="daily_demands")

    __table_args__ = (
        UniqueConstraint("dataset_id", "date_", "product_id", "city_name", name="uq_daily_demand_dataset_date_product_city"),
        Index("idx_daily_demand_dataset_product_date", "dataset_id", "product_id", "date_"),
        Index("idx_demand_product_date", "product_id", "date_"),
        Index("idx_demand_city_product", "city_name", "product_id"),
        Index("idx_daily_demand_upload_job_id", "upload_job_id"),
    )
