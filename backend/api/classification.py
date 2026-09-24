"""
backend/api/classification.py
------------------------------
Router for ABC-XYZ Segmentation & Policy Differentiation (Prompt 4.7)
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.core.deps import get_current_user_or_guest
from backend.models.user import User
from backend.services.classification_service import (
    run_abc_xyz_classification,
    get_abc_xyz_matrix,
    get_skus_for_cell,
    update_cell_policy,
)
from backend.models.classification import AbcXyzPolicy

router = APIRouter()


class PolicyUpdateRequest(BaseModel):
    review_strategy: Optional[str] = None
    target_service_level: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    safety_stock_policy: Optional[str] = None
    reorder_automation: Optional[str] = None
    review_frequency_days: Optional[int] = Field(default=None, ge=1)
    description: Optional[str] = None


class RecomputeClassificationRequest(BaseModel):
    dataset_id: Optional[int] = None
    a_cut: float = Field(default=0.80, gt=0.0, lt=1.0)
    b_cut: float = Field(default=0.95, gt=0.0, lt=1.0)
    x_cut: float = Field(default=0.25, gt=0.0)
    y_cut: float = Field(default=1.00, gt=0.0)


@router.get("/matrix")
def get_matrix(
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns the 3x3 ABC-XYZ grid with SKU counts, total annual consumption values,
    value percentages, and associated cell policies.
    """
    return get_abc_xyz_matrix(db, dataset_id=dataset_id)


@router.get("/skus")
def get_skus_by_cell(
    cell: str = Query(default="AX", pattern="^[A-C][X-Z]$"),
    dataset_id: Optional[int] = Query(default=None),

    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Drill down into a specific cell (e.g. AX, AY, etc.) to list SKUs,
    their consumption value, demand predictability CV^2, and active policy.
    """
    return get_skus_for_cell(
        db=db,
        dataset_id=dataset_id,
        cell=cell,
        limit=limit,
        offset=offset
    )


@router.get("/policies")
def get_all_policies(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Returns the current 9-cell policy configuration table.
    """
    policies = db.query(AbcXyzPolicy).order_by(AbcXyzPolicy.cell.asc()).all()
    return {
        "status": "success",
        "policies": [
            {
                "cell": p.cell,
                "abc_class": p.abc_class,
                "xyz_class": p.xyz_class,
                "review_strategy": p.review_strategy,
                "target_service_level": p.target_service_level,
                "safety_stock_policy": p.safety_stock_policy,
                "reorder_automation": p.reorder_automation,
                "review_frequency_days": p.review_frequency_days,
                "description": p.description,
            }
            for p in policies
        ]
    }


@router.put("/policies/{cell}")
def update_policy(
    cell: str,
    payload: PolicyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Updates the policy configuration for a specific cell (e.g. AX, BY).
    """
    if len(cell) != 2 or cell[0] not in "ABC" or cell[1] not in "XYZ":
        raise HTTPException(status_code=400, detail=f"Invalid cell '{cell}'. Must be in AX..CZ.")

    return update_cell_policy(
        db=db,
        cell=cell,
        review_strategy=payload.review_strategy,
        target_service_level=payload.target_service_level,
        safety_stock_policy=payload.safety_stock_policy,
        reorder_automation=payload.reorder_automation,
        review_frequency_days=payload.review_frequency_days,
        description=payload.description,
    )


@router.post("/recompute")
def recompute_classification(
    payload: RecomputeClassificationRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Recalculates ABC-XYZ segmentation with custom Pareto cuts or CV^2 thresholds.
    """
    return run_abc_xyz_classification(
        db=db,
        dataset_id=payload.dataset_id,
        a_cut=payload.a_cut,
        b_cut=payload.b_cut,
        x_cut=payload.x_cut,
        y_cut=payload.y_cut,
    )
