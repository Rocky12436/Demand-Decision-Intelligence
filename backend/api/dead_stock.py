"""
backend/api/dead_stock.py
-------------------------
Router for Dead Stock, Capital Liability & Downward Clearance Actions (Prompt 4.8)
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.core.deps import get_current_user_or_guest
from backend.models.user import User
from backend.services.dead_stock_service import (
    scan_and_record_dead_stock,
    get_dead_stock_summary,
    get_dead_stock_items,
    execute_dead_stock_action,
)

router = APIRouter()


class DeadStockScanRequest(BaseModel):
    dataset_id: Optional[int] = None
    inactivity_days_threshold: int = Field(default=90, ge=30, le=730)
    cover_days_threshold: int = Field(default=180, ge=60, le=1000)


class ApplyActionRequest(BaseModel):
    action_taken: str = Field(..., description="MARKDOWN, TRANSFER, BUNDLE, RETURN_TO_SUPPLIER, WRITE_OFF, DELIST, DISMISS")
    discount_pct: Optional[float] = Field(default=None, ge=0.0, le=0.90)
    notes: Optional[str] = None


@router.get("/summary")
def get_summary(
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns headline numbers: Total Capital Locked Up, monthly storage drain,
    and action breakdown.
    """
    return get_dead_stock_summary(db, dataset_id=dataset_id)


@router.get("/items")
def get_items(
    dataset_id: Optional[int] = Query(default=None),
    action: Optional[str] = Query(default=None),
    location: Optional[str] = Query(default=None),
    min_days_inactive: int = Query(default=0, ge=0),
    status: str = Query(default="PENDING"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns filterable, paginated list of dead stock items with suggested actions.
    """
    return get_dead_stock_items(
        db=db,
        dataset_id=dataset_id,
        action=action,
        location=location,
        min_days_inactive=min_days_inactive,
        status=status,
        limit=limit,
        offset=offset
    )


@router.post("/scan")
def trigger_dead_stock_scan(
    payload: DeadStockScanRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Scans the catalog for inactive SKUs (>= 90 days) or excessive forward cover (>= 180 days)
    and computes capital tied up and markdown discounts.
    """
    return scan_and_record_dead_stock(
        db=db,
        dataset_id=payload.dataset_id,
        inactivity_days_threshold=payload.inactivity_days_threshold,
        cover_days_threshold=payload.cover_days_threshold,
    )


@router.post("/{record_id}/action")
def apply_action(
    record_id: int,
    payload: ApplyActionRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Executes or dismisses a downward clearance action on a dead stock record.
    """
    try:
        return execute_dead_stock_action(
            db=db,
            record_id=record_id,
            action_taken=payload.action_taken,
            discount_pct=payload.discount_pct,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
