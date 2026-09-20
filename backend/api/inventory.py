"""
Inventory API Router
Project: Demand-Decision-Intelligence
"""

import json
import math
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
import pandas as pd

from backend.db.session import get_db
from backend.models.demand import DailyProductDemand
from backend.services.dataset_service import resolve_dataset

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


from datetime import datetime, timezone, date
from sqlalchemy import func
from backend.models.inventory import InventoryRecommendation
from backend.models.upload import UploadJob
from backend.services.forecast_service import check_historical_warning

from backend.services.inventory_service import (
    compute_inventory_recommendation_for_sku,
    compute_safety_stock_kings,
    compute_safety_stock_classical,
)

@router.get("/recommendations")
def get_inventory_recommendations(
    product_id: Optional[str] = None,
    city_name: Optional[str] = None,
    supplier_id: Optional[str] = None,
    dataset_id: Optional[int] = Query(default=None),
    as_of: Optional[date] = Query(default=None),
    use_classical: bool = Query(default=False, description="Use classical constant lead-time formula instead of King's formula"),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    """
    Returns calculated inventory optimization recommendations:
    Safety Stock (King's Formula with lead-time variability or classical), Reorder Point (ROP), Target Stock Level (TSL).
    Dynamically computes recommendations from the database scoped to the dataset if product_id is provided,
    otherwise returns precomputed deliverable sample dataset.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    latest_job = (
        db.query(UploadJob.id)
        .filter(UploadJob.status == "COMPLETED")
        .order_by(UploadJob.id.desc())
        .first()
    )
    latest_upload_id = latest_job[0] if latest_job else None

    if product_id:
        # Check staleness in DB
        stale_rec = (
            db.query(InventoryRecommendation)
            .filter(
                InventoryRecommendation.dataset_id == target_dataset.id,
                InventoryRecommendation.product_id == str(product_id),
                InventoryRecommendation.is_stale == True
            )
            .first()
        )
        is_stale = stale_rec is not None

        rec = compute_inventory_recommendation_for_sku(
            db=db,
            target_dataset=target_dataset,
            product_id=str(product_id),
            city_name=city_name,
            supplier_id=supplier_id,
            as_of=as_of,
            use_classical=use_classical,
        )
        if rec:
            return {
                "status": "success",
                "dataset_id": target_dataset.id,
                "total_returned": 1,
                "data": [rec],
                "as_of": rec["as_of"],
                "historical_warning": rec["historical_warning"],
                "freshness": {
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                    "data_through": rec["as_of"],
                    "is_stale": is_stale,
                    "model_name": f"King_SafetyStock_95 ({rec['formula_used']})",
                    "source_upload_job_id": latest_upload_id
                }
            }

    sample_file = REPORTS_DIR / "inventory_decision_sample.csv"
    if not sample_file.exists():
        raise HTTPException(status_code=404, detail="Inventory recommendations dataset not found.")

    df = pd.read_csv(sample_file).fillna(0)

    if product_id:
        df = df[df["product_id"].astype(str) == str(product_id)]
    if city_name:
        df = df[df["city_name"].astype(str).str.lower() == str(city_name).lower()]

    effective_as_of = as_of or target_dataset.date_max or date.today()
    hist_warn = check_historical_warning(effective_as_of)

    res_slice = df.head(limit).to_dict(orient="records")
    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total_returned": len(res_slice),
        "data": res_slice,
        "as_of": effective_as_of.isoformat(),
        "historical_warning": hist_warn,
        "freshness": {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "data_through": target_dataset.date_max.isoformat() if target_dataset.date_max else None,
            "is_stale": False,
            "model_name": "EOQ_SafetyStock_95",
            "source_upload_job_id": latest_upload_id
        }
    }


@router.get("/metadata")
def get_inventory_metadata():
    """
    Returns inventory engine metadata and configuration audit.
    """
    meta_file = REPORTS_DIR / "inventory_engine_metadata.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Inventory metadata file not found.")

    with open(meta_file, "r") as f:
        data = json.load(f)

    return {
        "status": "success",
        "metadata": data
    }
