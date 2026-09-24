"""
Explainability API Router (Prompt 5.4)
Project: Demand-Decision-Intelligence
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.explainability_service import get_sku_explainability_trace

router = APIRouter()


@router.get("/{product_id}")
def get_sku_explainability(
    product_id: str,
    dataset_id: Optional[int] = Query(default=None),
    city_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns the comprehensive, transparent explainability trace for any SKU:
    1. DATA — observations, date range, non-zero days, total quantity, quality flags.
    2. CLASSIFICATION — ADI, CV^2, SBC category, ABC-XYZ cell, and written rule.
    3. MODEL SELECTION — chosen model, candidates evaluated, and rejection rationales.
    4. FORECAST — point forecast, quantiles, and decomposition factors.
    5. POLICY ARITHMETIC — exact formulas with substituted numbers: LTD, SS, ROP, TSL.
    6. ACTIONS — trigger condition, recommendations, and risk status.
    """
    trace = get_sku_explainability_trace(
        db=db,
        product_id=product_id,
        dataset_id=dataset_id,
        city_name=city_name,
    )
    if trace.get("status") != "success":
        raise HTTPException(status_code=404, detail=f"SKU {product_id} explainability trace unavailable.")
    return trace
