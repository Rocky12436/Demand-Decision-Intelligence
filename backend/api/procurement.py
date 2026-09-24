"""
backend/api/procurement.py
--------------------------
API routes for Purchase Orders, MOQ/pack-size rounding generation,
PDF export, CSV export, email dispatch, and Goods Receipt processing (Prompt 4.1).
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db, enforce_writable_db
from backend.core.deps import get_current_user, require_role, get_current_user_or_guest
from backend.models.user import User
from backend.models.procurement import PurchaseOrder, Supplier, SupplierProduct
from backend.services.procurement_service import (
    generate_draft_purchase_orders,
    generate_po_pdf,
    export_po_csv,
    send_po_email,
)
from backend.services.recommendation_lifecycle import process_goods_receipt_learning_loop

router = APIRouter(prefix="/purchase-orders", tags=["Procurement & Purchase Orders"])


class GeneratePORequest(BaseModel):
    dataset_id: int = 1
    recommendation_ids: Optional[List[int]] = None


class GoodsReceiptLineItem(BaseModel):
    po_line_id: int
    quantity: int
    condition_notes: Optional[str] = "Good"


class RecordReceiptRequest(BaseModel):
    lines: List[GoodsReceiptLineItem]
    notes: Optional[str] = None


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate_pos(
    payload: GeneratePORequest,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(require_role(["admin", "manager"])),
):
    """
    Generates DRAFT POs grouped by preferred supplier with quantities
    rounded UP to order_multiple and floored at MOQ.
    """
    user_id = current_user.id if current_user else None
    results = generate_draft_purchase_orders(
        dataset_id=payload.dataset_id,
        db=db,
        created_by_user_id=user_id,
        specific_recommendation_ids=payload.recommendation_ids
    )
    return {
        "status": "success",
        "created_orders_count": len(results),
        "purchase_orders": results
    }


@router.get("")
def list_purchase_orders(
    dataset_id: Optional[int] = 1,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Lists purchase orders with supplier and line count information."""
    query = db.query(PurchaseOrder)
    if dataset_id:
        query = query.filter(PurchaseOrder.dataset_id == dataset_id)
    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter.lower())

    pos = query.order_by(PurchaseOrder.created_at.desc()).limit(100).all()
    results = []
    for po in pos:
        results.append({
            "id": po.id,
            "po_number": po.po_number,
            "supplier_id": po.supplier_id,
            "supplier_name": po.supplier.name if po.supplier else "N/A",
            "status": po.status,
            "total_value": po.total_value,
            "currency": po.currency,
            "created_at": po.created_at.isoformat() if po.created_at else None,
            "expected_delivery_date": po.expected_delivery_date.isoformat() if po.expected_delivery_date else None,
            "line_count": len(po.lines),
            "triggered_by": po.triggered_by,
            "notes": po.notes
        })
    return {"purchase_orders": results}


@router.get("/{po_id}")
def get_purchase_order_details(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Retrieves single PO with full line items and reason codes."""
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    lines = []
    for l in po.lines:
        lines.append({
            "id": l.id,
            "product_id": l.product_id,
            "product_name": l.product.product_name if l.product else l.product_id,
            "quantity_ordered": l.quantity_ordered,
            "quantity_received": l.quantity_received,
            "unit_cost": l.unit_cost,
            "line_total": l.line_total,
            "reason_code": l.reason_code,
            "context_data": l.context_data
        })

    return {
        "id": po.id,
        "po_number": po.po_number,
        "supplier": {
            "id": po.supplier.id if po.supplier else None,
            "name": po.supplier.name if po.supplier else "N/A",
            "email": po.supplier.contact_email if po.supplier else None,
            "phone": po.supplier.contact_phone if po.supplier else None,
            "payment_terms_days": po.supplier.payment_terms_days if po.supplier else 30
        },
        "status": po.status,
        "total_value": po.total_value,
        "currency": po.currency,
        "created_at": po.created_at.isoformat() if po.created_at else None,
        "expected_delivery_date": po.expected_delivery_date.isoformat() if po.expected_delivery_date else None,
        "lines": lines
    }


@router.get("/{po_id}/pdf")
def download_po_pdf(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Streams formatted ReportLab PDF for the Purchase Order."""
    pdf_bytes = generate_po_pdf(po_id, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=PO_{po_id}.pdf"}
    )


@router.get("/{po_id}/csv")
def download_po_csv(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Exports Purchase Order lines in standard CSV format."""
    csv_str = export_po_csv(po_id, db)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=PO_{po_id}.csv"}
    )


@router.post("/{po_id}/email")
def dispatch_po_email(
    po_id: int,
    dry_run: bool = True,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(require_role(["admin", "manager"])),
):
    """Dispatches Purchase Order email (dry-run mode by default)."""
    return send_po_email(po_id=po_id, db=db, dry_run=dry_run)


@router.post("/{po_id}/receipt")
def record_goods_receipt(
    po_id: int,
    payload: RecordReceiptRequest,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(require_role(["admin", "manager"])),
):
    """
    Records received goods against PO line items and triggers THE LEARNING LOOP,
    updating lead time observations and recalculating King's safety stock.
    """
    user_id = current_user.id if current_user else None
    lines_data = [l.model_dump() for l in payload.lines]
    return process_goods_receipt_learning_loop(
        po_id=po_id,
        receipt_lines=lines_data,
        received_by_user_id=user_id,
        db=db,
        notes=payload.notes
    )
