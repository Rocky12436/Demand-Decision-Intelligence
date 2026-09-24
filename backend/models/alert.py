"""
backend/models/alert.py
-----------------------
SQLAlchemy models for Alert Rules and Alert Notifications with SHA-256 Deduplication (Prompt 4.4).
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    type = Column(String(50), nullable=False, index=True) # STOCKOUT_RISK, BELOW_ROP, OVERSTOCK, etc.
    threshold_json = Column(JSON, nullable=True)
    channels = Column(JSON, nullable=False, default=list)  # ["in_app", "email", "whatsapp"]
    is_active = Column(Boolean, nullable=False, default=True)
    quiet_hours_start = Column(Integer, nullable=True) # Hour in 0-23
    quiet_hours_end = Column(Integer, nullable=True)   # Hour in 0-23
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    alerts = relationship("AlertNotification", back_populates="rule", cascade="all, delete-orphan")


class AlertNotification(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=True, index=True)
    type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="warning", index=True) # info, warning, critical
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    payload_json = Column(JSON, nullable=True)
    fired_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    dedup_key = Column(String(64), nullable=False, index=True) # SHA-256 of (type, product_id, city, bucket_date)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    rule = relationship("AlertRule", back_populates="alerts")
    product = relationship("Product")
