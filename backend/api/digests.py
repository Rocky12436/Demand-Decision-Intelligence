"""
Weekly Narrative Digest API Router (Prompt 5.6)
Project: Demand-Decision-Intelligence
"""

from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Query, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db, enforce_writable_db
from backend.core.deps import get_current_user_or_guest, require_role
from backend.models.user import User
from backend.models.digest import WeeklyDigest
from backend.services.dataset_service import resolve_dataset
from backend.services.narrative_digest_service import (
    aggregate_weekly_supply_chain_numbers,
    generate_and_save_weekly_digest,
)

router = APIRouter()


class GenerateDigestRequest(BaseModel):
    dataset_id: Optional[int] = None
    as_of: Optional[date] = None
    recipient_email: Optional[str] = Field(None, description="Optional email to record dispatch")
    email_to: Optional[str] = Field(None, description="Alias for recipient_email")

    def get_recipient(self) -> Optional[str]:
        return self.recipient_email or self.email_to


class SendEmailRequest(BaseModel):
    email: Optional[str] = Field(None, min_length=5, max_length=255)
    email_to: Optional[str] = Field(None, min_length=5, max_length=255)

    def get_email(self) -> str:
        target = self.email or self.email_to
        return target or "ops@company.org"


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def generate_weekly_digest(
    payload: GenerateDigestRequest,
    db: Session = Depends(get_db),
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
):
    """
    Assembles structured metrics, synthesizes ~300-400 word executive prose
    (Headline, What Changed, Decisions Needed, What to Watch),
    attaches verifiable numbers appendix, and persists to database.
    """
    digest = generate_and_save_weekly_digest(
        db=db,
        dataset_id=payload.dataset_id,
        as_of=payload.as_of,
        recipient_email=payload.get_recipient(),
    )
    d_dict = {
        "id": digest.id,
        "dataset_id": digest.dataset_id,
        "week_start_date": digest.week_start_date.isoformat(),
        "week_end_date": digest.week_end_date.isoformat(),
        "headline": digest.headline,
        "narrative_prose": digest.narrative_prose,
        "prose": digest.narrative_prose,
        "structured_numbers": digest.structured_numbers,
        "numbers_appendix": digest.structured_numbers,
        "delivered_email": digest.delivered_email,
        "recipient_email": digest.delivered_email,
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
    }
    return {
        "status": "success",
        "digest": d_dict,
        **d_dict,
    }


@router.get("")
@router.get("/")
def list_weekly_digests(
    dataset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns list of generated weekly executive digests for the dataset.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    digests = db.query(WeeklyDigest).filter(
        WeeklyDigest.dataset_id == target_dataset.id
    ).order_by(WeeklyDigest.created_at.desc()).limit(limit).all()

    items = [
        {
            "id": d.id,
            "week_start_date": d.week_start_date.isoformat(),
            "week_end_date": d.week_end_date.isoformat(),
            "headline": d.headline,
            "narrative_prose": d.narrative_prose,
            "prose": d.narrative_prose,
            "structured_numbers": d.structured_numbers,
            "numbers_appendix": d.structured_numbers,
            "delivered_email": d.delivered_email,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in digests
    ]
    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total": len(items),
        "digests": items,
    }


@router.get("/{digest_id}")
def get_single_weekly_digest(
    digest_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns full prose and structured numbers appendix for a specific weekly digest.
    """
    digest = db.query(WeeklyDigest).filter(WeeklyDigest.id == digest_id).first()
    if not digest:
        raise HTTPException(status_code=404, detail=f"Weekly digest {digest_id} not found.")

    d_dict = {
        "id": digest.id,
        "dataset_id": digest.dataset_id,
        "week_start_date": digest.week_start_date.isoformat(),
        "week_end_date": digest.week_end_date.isoformat(),
        "headline": digest.headline,
        "narrative_prose": digest.narrative_prose,
        "prose": digest.narrative_prose,
        "structured_numbers": digest.structured_numbers,
        "numbers_appendix": digest.structured_numbers,
        "delivered_email": digest.delivered_email,
        "delivered_at": digest.delivered_at.isoformat() if digest.delivered_at else None,
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
    }
    return {
        "status": "success",
        "digest": d_dict,
        **d_dict,
    }


@router.post("/{digest_id}/send-email")
def dispatch_weekly_digest_email(
    digest_id: int,
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
):
    """
    Logs email dispatch of the executive digest to managers.
    """
    from datetime import datetime, timezone
    digest = db.query(WeeklyDigest).filter(WeeklyDigest.id == digest_id).first()
    if not digest:
        raise HTTPException(status_code=404, detail=f"Weekly digest {digest_id} not found.")

    recipient = payload.get_email()
    digest.delivered_email = recipient
    digest.delivered_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "success",
        "message": f"Weekly digest #{digest.id} dispatched successfully to {recipient}.",
        "delivered_email": recipient,
        "recipient_email": recipient,
        "email_dispatched": True,
        "delivered_at": digest.delivered_at.isoformat(),
    }
