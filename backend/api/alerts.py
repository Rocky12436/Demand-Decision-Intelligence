"""
backend/api/alerts.py
---------------------
API routes for Alert Engine: evaluation, deduplication, acknowledging,
snoozing, digest generation, and unread badge counts (Prompt 4.4).
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db, enforce_writable_db
from backend.core.deps import get_current_user, require_role, get_current_user_or_guest
from backend.models.user import User
from backend.models.alert import AlertRule, AlertNotification
from backend.services.alerting_service import evaluate_system_alerts, generate_daily_alert_digest

router = APIRouter(prefix="/alerts", tags=["Alerting Engine"])


class SnoozeAlertRequest(BaseModel):
    snooze_hours: int = 24


@router.get("")
def list_alerts(
    dataset_id: Optional[int] = 1,
    severity: Optional[str] = None,
    unacknowledged_only: bool = False,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Lists alerts with severity gating, deduplication state, and snoozed checks."""
    now = datetime.now(timezone.utc)
    query = db.query(AlertNotification)
    if dataset_id:
        query = query.filter(AlertNotification.dataset_id == dataset_id)
    if severity:
        query = query.filter(AlertNotification.severity == severity.lower())
    if unacknowledged_only:
        query = query.filter(AlertNotification.acknowledged_at == None)

    # Filter out snoozed
    query = query.filter(
        (AlertNotification.snoozed_until == None) | (AlertNotification.snoozed_until < now)
    )

    alerts = query.order_by(AlertNotification.fired_at.desc()).limit(100).all()

    # If no alerts exist, trigger initial evaluation
    if not alerts and dataset_id:
        evaluate_system_alerts(dataset_id=dataset_id, db=db)
        alerts = query.order_by(AlertNotification.fired_at.desc()).limit(100).all()

    results = []
    for a in alerts:
        results.append({
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "title": a.title,
            "body": a.body,
            "product_id": a.product_id,
            "product_name": a.product.product_name if a.product else None,
            "payload": a.payload_json,
            "fired_at": a.fired_at.isoformat() if a.fired_at else None,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "snoozed_until": a.snoozed_until.isoformat() if a.snoozed_until else None,
        })
    return {"alerts": results}


@router.get("/unread-count")
def get_unread_alerts_count(
    dataset_id: Optional[int] = 1,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Returns number of unacknowledged and active alerts for the header bell badge."""
    now = datetime.now(timezone.utc)
    query = db.query(AlertNotification).filter(
        AlertNotification.acknowledged_at == None,
        (AlertNotification.snoozed_until == None) | (AlertNotification.snoozed_until < now)
    )
    if dataset_id:
        query = query.filter(AlertNotification.dataset_id == dataset_id)

    count = query.count()
    critical_count = query.filter(AlertNotification.severity == "critical").count()
    return {
        "unread_count": count,
        "critical_count": critical_count
    }


@router.post("/evaluate")
def run_alert_evaluation(
    dataset_id: int = 1,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(require_role(["admin", "manager"])),
):
    """Evaluates the 10 alert types against current inventory, stock, and forecast health."""
    return evaluate_system_alerts(dataset_id=dataset_id, db=db)


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Marks an alert as acknowledged by user."""
    alert = db.query(AlertNotification).filter(AlertNotification.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.id if current_user else None
    db.commit()
    return {"status": "acknowledged", "alert_id": alert.id, "acknowledged_at": alert.acknowledged_at.isoformat()}


@router.post("/{alert_id}/snooze")
def snooze_alert(
    alert_id: int,
    payload: SnoozeAlertRequest,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """Temporarily snoozes an alert for a specified duration."""
    alert = db.query(AlertNotification).filter(AlertNotification.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    until = datetime.now(timezone.utc) + timedelta(hours=payload.snooze_hours)
    alert.snoozed_until = until
    db.commit()
    return {"status": "snoozed", "alert_id": alert.id, "snoozed_until": until.isoformat()}


@router.get("/digest")
def get_daily_digest(
    dataset_id: int = 1,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """DIGEST MODE: Returns batched non-critical alerts for consolidated reporting."""
    return generate_daily_alert_digest(dataset_id=dataset_id, db=db)
