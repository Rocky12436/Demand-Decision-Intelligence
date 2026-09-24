"""
Data Quality API Router (Prompt 5.9)
Project: Demand-Decision-Intelligence
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.data_quality_service import (
    compute_dataset_quality_scorecard,
    get_data_quality_history,
)

router = APIRouter()


@router.get("/scorecard")
def get_quality_scorecard(
    dataset_id: Optional[int] = Query(default=None),
    upload_job_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns the comprehensive 0-100 Data Quality Scorecard across 10 dimensions,
    verifying if data passes the quality gate (>= 50) for advanced statistical modeling.
    """
    return compute_dataset_quality_scorecard(
        db=db,
        dataset_id=dataset_id,
        upload_job_id=upload_job_id,
    )


@router.get("/history")
def get_quality_trends(
    dataset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
):
    """
    Returns the data hygiene trajectory across uploads to audit data improvement over time.
    """
    return get_data_quality_history(
        db=db,
        dataset_id=dataset_id,
        limit=limit,
    )
