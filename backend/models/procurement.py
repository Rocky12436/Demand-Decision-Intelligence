"""
backend/models/procurement.py
------------------------------
SQLAlchemy models for Suppliers, Supplier Products, Purchase Orders,
PO Line Items, and Goods Receipts (Prompt 4.1).
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    payment_terms_days = Column(Integer, nullable=False, default=30)
    min_order_value = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    products = relationship("SupplierProduct", back_populates="supplier", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    unit_cost = Column(Float, nullable=False, default=10.0)
    moq = Column(Integer, nullable=False, default=1)               # Minimum order quantity
    order_multiple = Column(Integer, nullable=False, default=1)    # Pack size
    promised_lead_time_days = Column(Integer, nullable=False, default=5)
    is_preferred = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    supplier = relationship("Supplier", back_populates="products")
    product = relationship("Product")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, default=1, index=True)
    po_number = Column(String(100), nullable=False, unique=True, index=True)  # e.g. PO-2026-0001
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(
        String(50),
        nullable=False,
        default="draft",
        index=True
    )  # draft, pending_approval, approved, issued, partially_received, received, cancelled
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    expected_delivery_date = Column(DateTime(timezone=True), nullable=True)
    total_value = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), nullable=False, default="INR")
    notes = Column(Text, nullable=True)
    triggered_by = Column(String(50), nullable=False, default="rop_breach") # rop_breach, price_signal, manual, transfer
    source_policy_id = Column(String(100), nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan")
    receipts = relationship("GoodsReceipt", back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_received = Column(Integer, nullable=False, default=0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    line_total = Column(Float, nullable=False, default=0.0)
    reason_code = Column(String(100), nullable=False, default="ROP_BREACH")
    context_data = Column(Text, nullable=True)  # JSON formatted current_stock, rop, tsl, forecast_demand, lead_time

    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    product = relationship("Product")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    received_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    purchase_order = relationship("PurchaseOrder", back_populates="receipts")
    lines = relationship("GoodsReceiptLine", back_populates="goods_receipt", cascade="all, delete-orphan")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(Integer, ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    po_line_id = Column(Integer, ForeignKey("purchase_order_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    condition_notes = Column(String(255), nullable=True)

    goods_receipt = relationship("GoodsReceipt", back_populates="lines")
    po_line = relationship("PurchaseOrderLine")
