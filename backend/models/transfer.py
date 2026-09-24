"""
backend/models/transfer.py
--------------------------
SQLAlchemy models for Locations, Transfer Lanes, and Inter-City Transfer Orders (Prompt 4.5).
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city_name = Column(String(100), nullable=False, unique=True, index=True)
    location_type = Column(String(50), nullable=False, default="warehouse") # warehouse, store
    address = Column(Text, nullable=True)
    lat = Column(Float, nullable=False, default=12.9716) # Default Bengaluru
    lng = Column(Float, nullable=False, default=77.5946)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TransferLane(Base):
    __tablename__ = "transfer_lanes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    to_location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    transit_days = Column(Integer, nullable=False, default=2)
    cost_per_unit = Column(Float, nullable=False, default=1.5)
    cost_fixed = Column(Float, nullable=False, default=200.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])


class TransferOrder(Base):
    __tablename__ = "transfer_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    from_location_id = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    to_location_id = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(
        String(50),
        nullable=False,
        default="draft",
        index=True
    ) # draft, approved, in_transit, received, cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expected_arrival = Column(DateTime(timezone=True), nullable=True)
    total_cost = Column(Float, nullable=False, default=0.0)

    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
    lines = relationship("TransferOrderLine", back_populates="transfer_order", cascade="all, delete-orphan")


class TransferOrderLine(Base):
    __tablename__ = "transfer_order_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transfer_order_id = Column(Integer, ForeignKey("transfer_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=True)

    transfer_order = relationship("TransferOrder", back_populates="lines")
    product = relationship("Product")
