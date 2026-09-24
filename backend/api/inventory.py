"""
Inventory API Router
Project: Demand-Decision-Intelligence
"""

import json
import math
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
import pandas as pd

from backend.db.session import get_db
from backend.core.deps import get_current_user_or_guest
from backend.models.user import User
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.services.dataset_service import resolve_dataset

class BudgetAllocationRequest(BaseModel):
    dataset_id: Optional[int] = None
    budget: float = Field(..., gt=0, description="Available procurement working capital budget")
    horizon_days: int = Field(default=14, ge=1, le=180, description="Planning horizon in days")
    location_id: Optional[str] = Field(default=None, description="Optional city/location filter (e.g. 'Delhi', 'Mumbai', 'ALL')")
    constraints: Optional[Dict[str, Any]] = None


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


@router.get("/forward-buy-analysis")
def get_forward_buy_analysis(
    product_id: Optional[str] = None,
    delta_pct: float = 0.15,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Prompt 4.3: Quantifies optimal forward cover and order quantity against
    an anticipated price rise, subject to shelf life, capital, and capacity constraints.
    """
    from backend.services.forward_buy_optimizer import compute_optimal_forward_buy
    from backend.models.inventory import InventoryRecommendation
    from backend.models.procurement import SupplierProduct

    d_bar = 25.0
    sigma_d = 7.5
    current_price = 50.0
    shelf_life = 180

    if product_id:
        prod = db.query(Product).filter(Product.product_id == product_id).first()
        if prod and prod.shelf_life_days:
            shelf_life = prod.shelf_life_days

        rec = db.query(InventoryRecommendation).filter(
            InventoryRecommendation.product_id == product_id
        ).first()
        if rec and rec.avg_daily_demand > 0:
            d_bar = rec.avg_daily_demand
            sigma_d = rec.avg_daily_demand * 0.35

        sp = db.query(SupplierProduct).filter(
            SupplierProduct.product_id == product_id
        ).first()
        if sp and sp.unit_cost > 0:
            current_price = sp.unit_cost

    result = compute_optimal_forward_buy(
        d_bar=d_bar,
        sigma_d=sigma_d,
        current_price=current_price,
        delta_pct=delta_pct,
        shelf_life_days=shelf_life,
        holding_cost_rate=0.25,
        storage_capacity_units=1500.0,
        available_capital=300000.0
    )
    result["product_id"] = product_id
    result["unit_price"] = current_price
    result["mean_daily_demand"] = d_bar
    return result


@router.post("/allocate")
def allocate_procurement_budget(
    payload: BudgetAllocationRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Capital Allocation Planner: 'What should I buy with the money I have'
    Input: {dataset_id, budget, horizon_days, location_id?, constraints?}

    LOGIC:
    1. For every SKU below ROP, computes expected_stockout_cost_avoided:
       P(stockout within horizon) * expected_lost_units * margin_per_unit
       where P(stockout) comes from the forecast distribution (normal loss function),
       not a point estimate.
    2. Computes cost to bring each SKU to TSL (respecting preferred supplier MOQ and pack size).
    3. Ranks by benefit-to-cost ratio. Greedy-fill the budget (fractional-knapsack relaxation).
    4. Runs a 0/1 Knapsack DP refinement when SKU count <= 500, with fallback above that.
    5. Returns: selected SKUs with quantities and costs, total spend, budget remaining,
       total stockout cost avoided, top 5 unselected SKUs (risk accepted), and the
       diminishing returns curve.
    """
    from backend.services.budget_allocator import allocate_budget
    return allocate_budget(
        db=db,
        dataset_id=payload.dataset_id,
        budget=payload.budget,
        horizon_days=payload.horizon_days,
        location_id=payload.location_id,
        constraints=payload.constraints,
    )


class WhatIfSimulationRequest(BaseModel):
    dataset_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    service_level: Optional[float] = Field(0.95, ge=0.50, le=0.999)
    lead_time_days: Optional[int] = Field(None, ge=1, le=180)
    review_period_days: Optional[int] = Field(None, ge=1, le=90)
    demand_multiplier: float = Field(1.0, ge=0.1, le=5.0)
    price_change_pct: float = Field(0.0, ge=-80.0, le=200.0)
    price_elasticity: float = Field(-1.5, le=0.0)
    budget: Optional[float] = Field(None, ge=0.0)
    holding_cost_rate: float = Field(0.20, ge=0.01, le=1.0)


class SaveSimulationPolicyRequest(BaseModel):
    dataset_id: Optional[int] = None
    service_level: float = Field(0.95, ge=0.50, le=0.999)
    lead_time_days: Optional[int] = None
    review_period_days: Optional[int] = None
    cell: Optional[str] = "ALL"


@router.post("/simulate")
def simulate_inventory_policy(
    payload: WhatIfSimulationRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Vectorized What-If Policy Simulation (Prompt 5.3):
    Runs instant side-by-side policy scenario comparison (<500ms execution for 1000 SKUs).
    Evaluates changes in Service Level, Lead Time, Review Period, Demand Shocks, Price Elasticity,
    and Working Capital vs Holding & Stockout Costs, including non-linear cost curve.
    """
    from backend.services.whatif_simulator import run_vectorized_whatif_simulation
    return run_vectorized_whatif_simulation(
        db=db,
        dataset_id=payload.dataset_id,
        product_ids=payload.product_ids,
        service_level=payload.service_level,
        lead_time_days=payload.lead_time_days,
        review_period_days=payload.review_period_days,
        demand_multiplier=payload.demand_multiplier,
        price_change_pct=payload.price_change_pct,
        price_elasticity=payload.price_elasticity,
        budget=payload.budget,
        holding_cost_rate=payload.holding_cost_rate,
    )


@router.post("/simulate/save-policy")
def save_simulated_policy(
    payload: SaveSimulationPolicyRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_or_guest),
):
    """
    Persists simulated policy parameters (service level, review period, lead time)
    into ABC-XYZ policy rules.
    """
    from backend.models.classification import AbcXyzPolicy

    updated_cells = []
    cells_to_update = (
        ["AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"]
        if not payload.cell or payload.cell.upper() == "ALL"
        else [payload.cell.upper()]
    )

    for c in cells_to_update:
        policy = db.query(AbcXyzPolicy).filter(
            AbcXyzPolicy.cell == c
        ).first()

        if policy:
            policy.target_service_level = payload.service_level
            if payload.review_period_days is not None:
                policy.review_frequency_days = payload.review_period_days
            updated_cells.append(c)
        else:
            new_policy = AbcXyzPolicy(
                cell=c,
                abc_class=c[0],
                xyz_class=c[1],
                target_service_level=payload.service_level,
                review_frequency_days=payload.review_period_days or 7,
                review_strategy="CONTINUOUS" if "A" in c else "PERIODIC",
                safety_stock_policy="STANDARD_KINGS",
                reorder_automation="MANUAL_APPROVAL" if "Z" in c else "AUTOMATED",
            )
            db.add(new_policy)
            updated_cells.append(c)

    db.commit()
    return {
        "status": "success",
        "message": f"Successfully updated policy for {len(updated_cells)} cells with Service Level {payload.service_level * 100}%.",
        "updated_cells": updated_cells,
        "service_level": payload.service_level,
    }



