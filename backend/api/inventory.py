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


from datetime import datetime, timezone
from sqlalchemy import func
from backend.models.inventory import InventoryRecommendation
from backend.models.upload import UploadJob

@router.get("/recommendations")
def get_inventory_recommendations(
    product_id: Optional[str] = None,
    city_name: Optional[str] = None,
    dataset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    """
    Returns calculated inventory optimization recommendations:
    Safety Stock, Reorder Point (ROP), Target Stock Level (TSL), and Unit Landing Cost.
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

        query = db.query(DailyProductDemand).filter(
            DailyProductDemand.dataset_id == target_dataset.id,
            DailyProductDemand.product_id == str(product_id)
        )
        if city_name:
            query = query.filter(DailyProductDemand.city_name == city_name)

        records = query.order_by(DailyProductDemand.date_.asc()).all()
        if records:
            quantities = [float(r.total_quantity or 0.0) for r in records]
            avg_demand = sum(quantities) / len(quantities) if quantities else 0.0
            variance = sum((q - avg_demand) ** 2 for q in quantities) / len(quantities) if quantities else 0.0
            std_demand = math.sqrt(variance)

            lead_time_days = 7.0
            z_score = 1.645  # 95% service level
            safety_stock = round(z_score * std_demand * math.sqrt(lead_time_days), 2)
            reorder_point = round((avg_demand * lead_time_days) + safety_stock, 2)
            target_stock = round(reorder_point + (avg_demand * 7.0), 2)

            avg_price = records[-1].avg_unit_price if records[-1].avg_unit_price else 10.0
            unit_landing_cost = round(avg_price * 0.8, 2)

            rec = {
                "dataset_id": target_dataset.id,
                "dataset_name": target_dataset.name,
                "product_id": str(product_id),
                "city_name": city_name or (records[0].city_name if records else "Delhi"),
                "mean_daily_demand": round(avg_demand, 2),
                "std_daily_demand": round(std_demand, 2),
                "lead_time_days": lead_time_days,
                "service_level": 0.95,
                "safety_stock": safety_stock,
                "reorder_point": reorder_point,
                "target_stock_level": target_stock,
                "unit_landing_cost": unit_landing_cost,
                "stockout_risk_score": 0.05 if safety_stock > 0 else 0.5,
                "recommendation": "REORDER" if safety_stock > 0 else "MAINTAIN"
            }
            return {
                "status": "success",
                "dataset_id": target_dataset.id,
                "total_returned": 1,
                "data": [rec],
                "freshness": {
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                    "data_through": records[-1].date_.isoformat() if records else None,
                    "is_stale": is_stale,
                    "model_name": "EOQ_SafetyStock_95",
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

    res_slice = df.head(limit).to_dict(orient="records")
    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total_returned": len(res_slice),
        "data": res_slice,
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
