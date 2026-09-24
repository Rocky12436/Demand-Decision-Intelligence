"""
Indian Festival & Calendar API Router
Project: Demand-Decision-Intelligence
Phase 5 - Prompt 5.1
"""

from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db, enforce_writable_db
from backend.core.deps import require_role
from backend.models.user import User
from backend.services.dataset_service import resolve_dataset
from backend.services.festival_service import (
    get_calendar_events_for_range,
    run_festival_wape_backtest,
    create_custom_calendar_event,
    delete_calendar_event,
    CITY_TO_REGION,
)

router = APIRouter()


class CalendarEventCreateRequest(BaseModel):
    event_name: str = Field(..., min_length=2, max_length=150)
    event_date: date
    event_type: str = Field("regional_festival", description="national_holiday, religious_festival, regional_festival, school_holiday, month_end, payday")
    region: Optional[str] = Field(None, description="2-letter Indian state code (e.g. MH, DL, KA, TN) or null for national")
    impact_window_before: int = Field(1, ge=0, le=30)
    impact_window_after: int = Field(1, ge=0, le=30)
    is_moveable: bool = Field(False)


@router.get("/events")
def list_calendar_events(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    region: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Retrieves all Indian festival and calendar events for the specified date range and region.
    """
    s_date = start_date or date(2020, 1, 1)
    e_date = end_date or date(2030, 12, 31)
    events = get_calendar_events_for_range(
        db=db,
        start_date=s_date,
        end_date=e_date,
        region=region if region and region.upper() != "ALL" else None,
        event_type=event_type,
    )
    return {
        "status": "success",
        "total": len(events),
        "start_date": s_date.isoformat(),
        "end_date": e_date.isoformat(),
        "region": region,
        "events": [
            {
                "id": ev.id,
                "event_name": ev.event_name,
                "event_date": ev.event_date.isoformat(),
                "event_type": ev.event_type,
                "region": ev.region,
                "impact_window_before": ev.impact_window_before,
                "impact_window_after": ev.impact_window_after,
                "is_moveable": ev.is_moveable,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in events
        ],
    }


@router.post("/events", status_code=status.HTTP_201_CREATED)
def add_calendar_event(
    payload: CalendarEventCreateRequest,
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db)
):
    """
    Adds a custom festival, store anniversary, or promotional event.
    """
    event = create_custom_calendar_event(
        db=db,
        event_name=payload.event_name,
        event_date=payload.event_date,
        event_type=payload.event_type,
        region=payload.region.upper() if payload.region else None,
        impact_window_before=payload.impact_window_before,
        impact_window_after=payload.impact_window_after,
        is_moveable=payload.is_moveable,
    )
    return {
        "status": "success",
        "message": f"Calendar event '{event.event_name}' created successfully.",
        "event": {
            "id": event.id,
            "event_name": event.event_name,
            "event_date": event.event_date.isoformat(),
            "event_type": event.event_type,
            "region": event.region,
            "impact_window_before": event.impact_window_before,
            "impact_window_after": event.impact_window_after,
            "is_moveable": event.is_moveable,
        }
    }


@router.delete("/events/{event_id}")
def remove_calendar_event(
    event_id: int,
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db)
):
    """
    Deletes a calendar event by ID.
    """
    deleted = delete_calendar_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Calendar event {event_id} not found.")
    return {
        "status": "success",
        "message": f"Calendar event {event_id} deleted successfully."
    }


@router.get("/backtest")
def get_festival_backtest(
    dataset_id: Optional[int] = Query(None),
    product_ids: Optional[str] = Query(None, description="Comma-separated product IDs"),
    city_name: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Evaluates forecasting accuracy (WAPE) with vs without festival regressors per SKU.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    p_ids = [p.strip() for p in product_ids.split(",") if p.strip()] if product_ids else None

    result = run_festival_wape_backtest(
        db=db,
        dataset_id=target_dataset.id,
        product_ids=p_ids,
        city_name=city_name,
    )
    return result


@router.get("/regions")
def get_regions_and_mappings():
    """
    Returns supported city-to-state code regional calendar mappings.
    """
    return {
        "status": "success",
        "city_to_region": CITY_TO_REGION,
        "supported_states": sorted(list(set(CITY_TO_REGION.values()))),
        "event_types": [
            "national_holiday",
            "religious_festival",
            "regional_festival",
            "school_holiday",
            "month_end",
            "payday"
        ]
    }
