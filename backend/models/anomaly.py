from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base

class AnomalyAlert(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    anomaly_date = Column(Date, nullable=False, index=True)
    anomaly_type = Column(String(50), nullable=False, index=True)  # SPIKE, DROP, PRICE_DISCREPANCY, ZERO_STOCK_SURGE
    severity = Column(String(20), nullable=False, default="MEDIUM", index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    metric_name = Column(String(100), nullable=False)  # demand_quantity, unit_price, discount
    actual_value = Column(Float, nullable=False)
    expected_value = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="OPEN", index=True)  # OPEN, INVESTIGATING, RESOLVED, DISMISSED
    detection_method = Column(String(100), nullable=True)  # MODIFIED_Z_MAD, COUNT_MODEL_NEGBINOMIAL, INTERARRIVAL_GAP_SILENCE
    confidence = Column(String(20), nullable=True, default="MEDIUM")  # HIGH, MEDIUM, LOW, INSUFFICIENT_HISTORY
    is_stale = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product", back_populates="anomalies")

    __table_args__ = (
        Index("idx_anomaly_prod_date", "product_id", "anomaly_date"),
        Index("idx_anomaly_status_severity", "status", "severity"),
        Index("idx_anomaly_dataset_id", "dataset_id"),
    )
