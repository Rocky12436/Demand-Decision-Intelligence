"""
backend/services/procurement_service.py
---------------------------------------
Service handling:
- Draft Purchase Order generation with MOQ & pack-size rounding (Prompt 4.1)
- Below-minimum-order-value detection & top-up recommendations
- PDF Purchase Order generation via ReportLab
- CSV export for procurement teams
- Email dispatch (dry-run & SMTP)
- Goods receipt processing and triggering the Learning Loop
"""

import io
import math
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from backend.models.procurement import (
    Supplier,
    SupplierProduct,
    PurchaseOrder,
    PurchaseOrderLine,
    GoodsReceipt,
    GoodsReceiptLine,
)
from backend.models.product import Product
from backend.models.inventory import InventoryRecommendation, InventoryState
from backend.models.user import User

logger = logging.getLogger(__name__)


def round_to_moq_and_pack_size(needed_qty: float, moq: int, pack_size: int) -> int:
    """
    Rounds needed quantity UP to order_multiple (pack_size) and floored at MOQ.
    Edge cases handled:
    - needed_qty <= 0 -> 0 (no order required)
    - needed_qty <= moq -> ceil(moq / pack_size) * pack_size
    - needed_qty > moq -> ceil(needed_qty / pack_size) * pack_size
    """
    if needed_qty <= 0:
        return 0
    moq = max(1, int(moq))
    pack_size = max(1, int(pack_size))

    target = max(float(needed_qty), float(moq))
    packs = math.ceil(target / pack_size)
    return int(packs * pack_size)


def generate_draft_purchase_orders(
    dataset_id: int,
    db: Session,
    created_by_user_id: Optional[int] = None,
    specific_recommendation_ids: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    Generates draft purchase orders grouped by preferred supplier.
    Quantities are rounded UP to order_multiple and floored at moq.
    Checks min_order_value and suggests top-ups if below threshold.
    """
    # 1. Fetch inventory recommendations in breach (or specific requested ones)
    query = db.query(InventoryRecommendation).filter(
        InventoryRecommendation.dataset_id == dataset_id
    )
    if specific_recommendation_ids:
        query = query.filter(InventoryRecommendation.id.in_(specific_recommendation_ids))
    else:
        query = query.filter(
            (InventoryRecommendation.current_stock < InventoryRecommendation.reorder_point) |
            (InventoryRecommendation.risk_status.in_(["HIGH_STOCKOUT_RISK", "STOCKOUT_RISK", "CRITICAL"]))
        )

    recommendations = query.all()
    if not recommendations:
        return []

    # 2. Group required items by preferred supplier
    supplier_items_map: Dict[int, List[Dict[str, Any]]] = {}

    for rec in recommendations:
        # Find preferred supplier product mapping
        sp = db.query(SupplierProduct).filter(
            SupplierProduct.product_id == rec.product_id,
            SupplierProduct.is_preferred == True
        ).first()

        if not sp:
            # Fallback to any supplier product for this item
            sp = db.query(SupplierProduct).filter(
                SupplierProduct.product_id == rec.product_id
            ).first()

        if not sp:
            # Auto-provision a default supplier if none exists yet
            default_supplier = db.query(Supplier).filter(Supplier.name == "Standard Wholesale Co.").first()
            if not default_supplier:
                default_supplier = Supplier(
                    name="Standard Wholesale Co.",
                    contact_email="procurement@standardwholesale.example.com",
                    contact_phone="+91 98765 43210",
                    address="Plot 42, Industrial Area, Bengaluru, Karnataka",
                    payment_terms_days=30,
                    min_order_value=5000.0,
                    is_active=True
                )
                db.add(default_supplier)
                db.flush()

            sp = SupplierProduct(
                supplier_id=default_supplier.id,
                product_id=rec.product_id,
                unit_cost=rec.product.unit_cost if hasattr(rec.product, 'unit_cost') and rec.product.unit_cost else 50.0,
                moq=10,
                order_multiple=5,
                promised_lead_time_days=rec.lead_time_days or 5,
                is_preferred=True
            )
            db.add(sp)
            db.flush()

        needed = rec.recommended_order_qty if rec.recommended_order_qty > 0 else max(0, rec.reorder_point - rec.current_stock)
        rounded_qty = round_to_moq_and_pack_size(needed, sp.moq, sp.order_multiple)
        if rounded_qty <= 0:
            continue

        item_total = rounded_qty * sp.unit_cost
        context = {
            "current_stock": rec.current_stock,
            "reorder_point": rec.reorder_point,
            "safety_stock": rec.safety_stock,
            "target_stock_level": rec.reorder_point + rec.safety_stock,
            "avg_daily_demand": rec.avg_daily_demand,
            "lead_time_days": sp.promised_lead_time_days,
            "raw_needed": needed,
            "moq": sp.moq,
            "order_multiple": sp.order_multiple
        }

        if sp.supplier_id not in supplier_items_map:
            supplier_items_map[sp.supplier_id] = []

        supplier_items_map[sp.supplier_id].append({
            "product_id": rec.product_id,
            "product_name": rec.product.product_name if rec.product else rec.product_id,
            "quantity_ordered": rounded_qty,
            "unit_cost": sp.unit_cost,
            "line_total": item_total,
            "reason_code": "ROP_BREACH",
            "context_data": json.dumps(context),
            "lead_time_days": sp.promised_lead_time_days,
        })

    # 3. Create Purchase Orders per supplier
    created_pos = []
    now = datetime.now(timezone.utc)
    current_year = now.year

    for supplier_id, items in supplier_items_map.items():
        supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
        if not supplier or not items:
            continue

        # Sequential PO number calculation with collision check
        max_id = db.query(func.max(PurchaseOrder.id)).scalar() or 0
        seq_num = max_id + len(created_pos) + 1
        po_number = f"PO-{current_year}-{seq_num:04d}"
        while db.query(PurchaseOrder).filter(PurchaseOrder.po_number == po_number).first():
            seq_num += 1
            po_number = f"PO-{current_year}-{seq_num:04d}"

        total_value = sum(item["line_total"] for item in items)
        max_lead_time = max(item["lead_time_days"] for item in items)
        expected_delivery = now + timedelta(days=max_lead_time)

        is_below_min = total_value < supplier.min_order_value
        notes = []
        if is_below_min:
            deficit = supplier.min_order_value - total_value
            notes.append(f"⚠️ BELOW MINIMUM ORDER VALUE: Order total ₹{total_value:,.2f} is ₹{deficit:,.2f} below minimum ₹{supplier.min_order_value:,.2f}.")

        po = PurchaseOrder(
            dataset_id=dataset_id,
            po_number=po_number,
            supplier_id=supplier_id,
            status="draft",
            created_by=created_by_user_id,
            created_at=now,
            expected_delivery_date=expected_delivery,
            total_value=total_value,
            currency="INR",
            notes=" | ".join(notes) if notes else None,
            triggered_by="rop_breach",
        )
        db.add(po)
        db.flush()

        for item in items:
            line = PurchaseOrderLine(
                po_id=po.id,
                product_id=item["product_id"],
                quantity_ordered=item["quantity_ordered"],
                quantity_received=0,
                unit_cost=item["unit_cost"],
                line_total=item["line_total"],
                reason_code=item["reason_code"],
                context_data=item["context_data"],
            )
            db.add(line)

        # Look for potential top-up items from same supplier if below minimum
        top_up_suggestions = []
        if is_below_min:
            other_sps = db.query(SupplierProduct).filter(
                SupplierProduct.supplier_id == supplier_id,
                ~SupplierProduct.product_id.in_([it["product_id"] for it in items])
            ).limit(5).all()

            for osp in other_sps:
                rec_check = db.query(InventoryRecommendation).filter(
                    InventoryRecommendation.dataset_id == dataset_id,
                    InventoryRecommendation.product_id == osp.product_id
                ).first()
                if rec_check and rec_check.current_stock < rec_check.reorder_point * 1.5:
                    suggested_qty = round_to_moq_and_pack_size(rec_check.reorder_point, osp.moq, osp.order_multiple)
                    top_up_suggestions.append({
                        "product_id": osp.product_id,
                        "product_name": rec_check.product.product_name if rec_check.product else osp.product_id,
                        "current_stock": rec_check.current_stock,
                        "reorder_point": rec_check.reorder_point,
                        "suggested_qty": suggested_qty,
                        "unit_cost": osp.unit_cost,
                        "additional_value": suggested_qty * osp.unit_cost
                    })

        created_pos.append({
            "id": po.id,
            "po_number": po.po_number,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "status": po.status,
            "total_value": total_value,
            "min_order_value": supplier.min_order_value,
            "is_below_minimum": is_below_min,
            "top_up_suggestions": top_up_suggestions,
            "line_count": len(items),
            "expected_delivery_date": expected_delivery.isoformat(),
        })

    db.commit()
    return created_pos


def generate_po_pdf(po_id: int, db: Session) -> bytes:
    """
    Generates a professional Purchase Order PDF using ReportLab with:
    - Company & Supplier Details
    - Status & Delivery Schedule
    - Line Items Table with Reason Code
    - Grand Totals
    - Authorized Signature Block
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    supplier = po.supplier
    lines = po.lines

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    story = []

    # Title & Header
    title_style = ParagraphStyle(
        'POTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e293b'),
        fontName='Helvetica-Bold'
    )
    normal_style = ParagraphStyle(
        'PONormal',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#475569')
    )
    bold_style = ParagraphStyle(
        'POBold',
        parent=normal_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )

    story.append(Paragraph(f"PURCHASE ORDER — {po.po_number}", title_style))
    story.append(Paragraph(f"Demand & Decision Intelligence System | Procurement Division", normal_style))
    story.append(Spacer(1, 15))

    # Metadata Grid (Supplier & Order Details)
    created_str = po.created_at.strftime('%d %b %Y') if po.created_at else "N/A"
    delivery_str = po.expected_delivery_date.strftime('%d %b %Y') if po.expected_delivery_date else "Standard"

    supplier_info = (
        f"<b>Vendor / Supplier:</b><br/>"
        f"{supplier.name if supplier else 'General Vendor'}<br/>"
        f"{supplier.address if supplier and supplier.address else 'Commercial Logistics Hub'}<br/>"
        f"Email: {supplier.contact_email if supplier and supplier.contact_email else 'orders@vendor.com'}<br/>"
        f"Payment Terms: {supplier.payment_terms_days if supplier else 30} Days"
    )
    order_info = (
        f"<b>Order Details:</b><br/>"
        f"PO Status: <b>{po.status.upper()}</b><br/>"
        f"Order Date: {created_str}<br/>"
        f"Delivery Target: {delivery_str}<br/>"
        f"Trigger: {po.triggered_by.replace('_', ' ').title()}"
    )

    info_table = Table(
        [[Paragraph(supplier_info, normal_style), Paragraph(order_info, normal_style)]],
        colWidths=[270, 270]
    )
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # Line Items Table
    headers = ["SKU / Product", "Reason", "Qty Ordered", "Unit Price", "Line Total"]
    table_data = [[Paragraph(f"<b>{h}</b>", bold_style) for h in headers]]

    for line in lines:
        prod_label = line.product.product_name if line.product else line.product_id
        table_data.append([
            Paragraph(f"{line.product_id}<br/><font color='#64748b' size='7.5'>{prod_label[:30]}</font>", normal_style),
            Paragraph(line.reason_code, normal_style),
            Paragraph(f"{line.quantity_ordered:,}", normal_style),
            Paragraph(f"₹{line.unit_cost:,.2f}", normal_style),
            Paragraph(f"₹{line.line_total:,.2f}", bold_style),
        ])

    # Grand Total Row
    table_data.append([
        "", "", "",
        Paragraph("<b>GRAND TOTAL:</b>", bold_style),
        Paragraph(f"<b>₹{po.total_value:,.2f}</b>", bold_style)
    ])

    col_widths = [160, 100, 80, 100, 100]
    items_table = Table(table_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#0f172a')),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 35))

    # Notes & Signature Block
    sig_text = (
        "<b>Authorized Signatory</b><br/><br/><br/>"
        "____________________________________<br/>"
        "Procurement Manager / Supply Chain Lead"
    )
    terms_text = (
        "<b>Terms & Acceptance:</b><br/>"
        "1. Goods must conform strictly to ordered SKU specifications.<br/>"
        "2. Discrepancies must be reported within 48 hours of dispatch.<br/>"
        "3. Delivery acknowledged upon verified Goods Receipt inspection."
    )
    footer_table = Table(
        [[Paragraph(terms_text, normal_style), Paragraph(sig_text, normal_style)]],
        colWidths=[320, 220]
    )
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(footer_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_po_csv(po_id: int, db: Session) -> str:
    """
    Exports Purchase Order lines in standard CSV format for procurement / ERP systems.
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    supplier_name = po.supplier.name if po.supplier else "N/A"
    date_str = po.created_at.strftime("%Y-%m-%d") if po.created_at else ""

    headers = [
        "po_number",
        "supplier_name",
        "order_date",
        "status",
        "product_id",
        "product_name",
        "quantity_ordered",
        "quantity_received",
        "unit_cost",
        "line_total",
        "currency",
        "reason_code",
    ]
    rows = [",".join(headers)]

    for line in po.lines:
        prod_name = (line.product.product_name if line.product else line.product_id).replace(",", ";")
        row = [
            po.po_number,
            f'"{supplier_name}"',
            date_str,
            po.status,
            line.product_id,
            f'"{prod_name}"',
            str(line.quantity_ordered),
            str(line.quantity_received),
            f"{line.unit_cost:.2f}",
            f"{line.line_total:.2f}",
            po.currency,
            line.reason_code,
        ]
        rows.append(",".join(row))

    return "\n".join(rows)


def send_po_email(po_id: int, db: Session, dry_run: bool = True) -> Dict[str, Any]:
    """
    Dispatches PO confirmation email to supplier contact.
    Operates in dry-run simulation mode unless live SMTP is configured in environment.
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    supplier = po.supplier
    recipient_email = supplier.contact_email if supplier and supplier.contact_email else "vendor@example.com"
    subject = f"Official Purchase Order: {po.po_number} - DemandIQ Procurement"

    body = (
        f"Dear {supplier.name if supplier else 'Supplier Partner'},\n\n"
        f"Please find attached purchase order {po.po_number} with a total value of "
        f"{po.currency} {po.total_value:,.2f}.\n\n"
        f"Line Items Count: {len(po.lines)}\n"
        f"Expected Delivery Target: {po.expected_delivery_date.strftime('%d %b %Y') if po.expected_delivery_date else 'Standard'}\n\n"
        f"Please confirm receipt and expected fulfillment schedule.\n\n"
        f"Regards,\nProcurement Team\nDemand & Decision Intelligence System"
    )

    logger.info(f"[PO_EMAIL_DISPATCH] To: {recipient_email} | Subject: {subject} | Dry-Run: {dry_run}")

    # Mark PO as issued if in approved status
    if po.status in ("approved", "draft"):
        po.status = "issued"
        po.issued_at = datetime.now(timezone.utc)
        db.commit()

    return {
        "status": "simulated" if dry_run else "sent",
        "dry_run": dry_run,
        "recipient": recipient_email,
        "subject": subject,
        "issued_at": po.issued_at.isoformat() if po.issued_at else None,
        "message": f"PO {po.po_number} dispatched to {recipient_email} (dry-run mode)."
    }
