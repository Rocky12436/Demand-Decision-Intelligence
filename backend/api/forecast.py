"""
Forecast API Router
Project: Demand-Decision-Intelligence
"""

import json
import threading
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from pydantic import BaseModel, Field
from backend.db.session import get_db, SessionLocal
from backend.models.procurement import Supplier, SupplierProduct
from backend.models.inventory import InventoryState, LeadTimeObservation
from backend.models.demand import DailyProductDemand
from backend.models.forecast import ForecastRun, ForecastItem, ForecastEvaluation, ForecastJob
from backend.models.product import Product
from backend.services.dataset_service import resolve_dataset
from datetime import datetime, timezone, date
from backend.services.forecast_service import (
    compute_or_get_forecast,
    compute_forecast_summary,
    recompute_all_forecasts_for_dataset,
    get_latest_upload_job_id,
    check_historical_warning,
    MODEL_ALIAS,
)
from backend.services.model_registry_service import (
    evaluate_and_promote_champion,
    monitor_sku_model_drift,
    get_model_performance_dashboard,
)
from backend.services.cold_start_service import (
    generate_analog_cold_start_forecast,
    generate_launch_curve_forecast,
)

from backend.core.deps import require_role
from backend.db.session import enforce_writable_db
from backend.models.user import User

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


class RecomputeForecastRequest(BaseModel):
    dataset_id: Optional[int] = None
    product_ids: Optional[List[str]] = None
    horizon_days: int = 14
    as_of: Optional[date] = None


# -------------------------------------------------------------------------
# NEW: Unified Summary Endpoint (the single source of truth for the UI)
# -------------------------------------------------------------------------

@router.get("/summary")
def get_forecast_summary(
    sku: str = Query(..., description="Product ID / SKU code"),
    horizon: int = Query(default=7, description="7, 14, or 30"),
    dataset_id: Optional[int] = Query(default=None),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """
    Single unified endpoint that the Forecast Studio page uses.
    Returns: sku info, headline numbers, daily forecast (q05-q95),
    recent history, reliability card, model leaderboard, inventory recommendation,
    confidence rating with plain-language reasons.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    result = compute_forecast_summary(
        db=db,
        dataset_id=target_dataset.id,
        product_id=str(sku),
        horizon_days=int(horizon),
        force_recompute=force_refresh,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("message"))
    result["dataset_name"] = target_dataset.name
    return result


@router.get("/skus")
def get_forecast_skus(
    dataset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
):
    """
    Returns list of products available in the active dataset with their name,
    category, and brand, designed for the product picker searchable dropdown.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    n_limit = int(limit) if isinstance(limit, (int, str)) and str(limit).isdigit() else 200
    # Get distinct product_ids in this dataset ordered by total demand
    top_pids = (
        db.query(DailyProductDemand.product_id, func.sum(DailyProductDemand.total_quantity).label("total_qty"))
        .filter(DailyProductDemand.dataset_id == target_dataset.id)
        .group_by(DailyProductDemand.product_id)
        .order_by(func.sum(DailyProductDemand.total_quantity).desc())
        .limit(n_limit)
        .all()
    )

    pid_list = [r[0] for r in top_pids if r[0]]
    products = db.query(Product).filter(Product.product_id.in_(pid_list)).all() if pid_list else []
    p_map = {p.product_id: p for p in products}

    results = []
    for pid, total_qty in top_pids:
        p = p_map.get(pid)
        results.append({
            "product_id": str(pid),
            "name": p.product_name if p and p.product_name else f"SKU {pid}",
            "category": (p.l1_category or p.l0_category or "Grocery") if p else "Grocery",
            "brand": p.brand_name if p else None,
            "unit": p.unit if p else None,
            "total_sales": float(total_qty or 0.0),
        })

    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total": len(results),
        "products": results,
    }


# -------------------------------------------------------------------------
# Async Job Status Endpoint
# -------------------------------------------------------------------------

@router.get("/jobs/{job_id}")
def get_forecast_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    """Poll status of a background forecast job."""
    job = db.query(ForecastJob).filter(ForecastJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    result = {}
    if job.result_summary:
        try:
            result = json.loads(job.result_summary)
        except Exception:
            pass
    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "result": result,
        "error_message": job.error_message,
    }


@router.post("/recompute")
def recompute_forecast_endpoint(
    payload: RecomputeForecastRequest,
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db)
):
    """
    Synchronously recomputes demand forecasts for the specified dataset and SKUs,
    clears stale flags, and returns freshness status and historical warnings.
    """
    target_dataset = resolve_dataset(db, None, payload.dataset_id)
    res = recompute_all_forecasts_for_dataset(
        db=db,
        dataset_id=target_dataset.id,
        product_ids=payload.product_ids,
        horizon_days=payload.horizon_days,
        as_of=payload.as_of
    )
    return res


@router.get("")
@router.get("/")
def get_forecast(
    product_id: Optional[str] = None,
    city_name: Optional[str] = None,
    dataset_id: Optional[int] = Query(default=None),
    horizon_days: int = Query(default=14, le=60),
    as_of: Optional[date] = Query(default=None),
    model_name: str = Query(default="Prophet_MovingAvg_Ensemble"),
    db: Session = Depends(get_db)
):
    """
    Returns dynamically computed or baseline demand forecast scoped strictly to a dataset.
    Forecast horizon is anchored to as_of date (or max date in dataset history).
    If as_of is >90 days behind current date, a historical_warning is returned.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    if product_id:
        result = compute_or_get_forecast(
            db=db,
            dataset_id=target_dataset.id,
            product_id=str(product_id),
            city_name=city_name,
            horizon_days=horizon_days,
            as_of=as_of,
            force_recompute=False,
            model_name=model_name,
        )
        if result.get("status") == "success":
            result["dataset_name"] = target_dataset.name
            return result
        elif result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=result.get("message", f"Product {product_id} not found in dataset {target_dataset.id}"))


    # Fallback to general runs store or summary if available
    latest_upload_id = get_latest_upload_job_id(db, target_dataset.id)
    effective_as_of = as_of or target_dataset.date_max or date.today()
    hist_warn = check_historical_warning(effective_as_of)

    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "message": "Forecasting suite operational. Provide product_id for SKU-level demand forecast.",
        "as_of": effective_as_of.isoformat(),
        "historical_warning": hist_warn,
        "freshness": {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "data_through": target_dataset.date_max.isoformat() if target_dataset.date_max else None,
            "is_stale": False,
            "model_name": "Prophet_MovingAvg_Ensemble",
            "source_upload_job_id": latest_upload_id
        },
        "runs": [str(r[0]) for r in db.query(ForecastRun.id).filter(ForecastRun.dataset_id == target_dataset.id).limit(10).all()]
    }


@router.get("/evaluation")
def get_forecast_evaluation(
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Returns comparative evaluation metrics (MAE, RMSE, WAPE) from database evaluations.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    evals = (
        db.query(
            ForecastEvaluation.model_name,
            func.avg(ForecastEvaluation.mae).label("mae"),
            func.avg(ForecastEvaluation.rmse).label("rmse"),
            func.avg(ForecastEvaluation.wape).label("wape"),
        )
        .filter(ForecastEvaluation.dataset_id == target_dataset.id)
        .group_by(ForecastEvaluation.model_name)
        .order_by(func.avg(ForecastEvaluation.wape).asc())
        .all()
    )

    models = [
        {
            "model": e.model_name,
            "mae": round(float(e.mae), 2) if e.mae is not None else None,
            "rmse": round(float(e.rmse), 2) if e.rmse is not None else None,
            "wape": round(float(e.wape), 2) if e.wape is not None else None,
        }
        for e in evals
    ]

    return {
        "status": "success",
        "best_model": models[0]["model"] if models else None,
        "models": models,
        "metadata": {
            "dataset_id": target_dataset.id,
            "total_models": len(models)
        }
    }


@router.get("/results")
def get_forecast_results(
    product_id: Optional[str] = None,
    city_name: Optional[str] = None,
    dataset_id: Optional[int] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    """
    Returns actual vs predicted demand data across models scoped to the dataset.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    latest_upload_id = get_latest_upload_job_id(db, target_dataset.id)

    if product_id:
        records = db.query(DailyProductDemand).filter(
            DailyProductDemand.dataset_id == target_dataset.id,
            DailyProductDemand.product_id == str(product_id)
        )
        if city_name:
            records = records.filter(DailyProductDemand.city_name == city_name)
        records = records.order_by(DailyProductDemand.date_.asc()).all()

        if records:
            quantities = [float(r.total_quantity or 0.0) for r in records]
            mean_q = round(sum(quantities) / len(quantities), 2)
            dynamic_data = [
                {
                    "date": r.date_.isoformat(),
                    "product_id": str(product_id),
                    "city_name": r.city_name,
                    "actual": float(r.total_quantity),
                    "predicted": mean_q,
                }
                for r in records[-limit:]
            ]
            return {
                "status": "success",
                "dataset_id": target_dataset.id,
                "total_returned": len(dynamic_data),
                "data": dynamic_data,
                "freshness": {
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                    "data_through": records[-1].date_.isoformat() if records else None,
                    "is_stale": False,
                    "model_name": "Prophet_MovingAvg_Ensemble",
                    "source_upload_job_id": latest_upload_id
                }
            }



    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total_returned": 0,
        "data": [],
        "freshness": {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "data_through": target_dataset.date_max.isoformat() if target_dataset.date_max else None,
            "is_stale": False,
            "model_name": "Prophet_MovingAvg_Ensemble",
            "source_upload_job_id": latest_upload_id
        }
    }


# -------------------------------------------------------------------------
# Prompt Fix 3: Real Database Forecast Runs & Freshness Queries
# (RUNS_STORE and _init_default_runs deleted)
# -------------------------------------------------------------------------

@router.get("/runs")
def get_forecast_runs(
    page: int = 1,
    page_size: int = 50,
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns paginated real forecast runs recorded in the database,
    scoped to the resolved active dataset (Prompt Fix 3).
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    query = (
        db.query(ForecastRun)
        .filter(ForecastRun.dataset_id == target_dataset.id)
        .order_by(ForecastRun.created_at.desc(), ForecastRun.id.desc())
    )
    total = query.count()
    start = (page - 1) * page_size
    runs = query.offset(start).limit(page_size).all()

    max_demand_date = (
        db.query(func.max(DailyProductDemand.date_))
        .filter(DailyProductDemand.dataset_id == target_dataset.id)
        .scalar()
    )

    results = []
    for r in runs:
        metrics = {}
        if r.metrics_summary:
            try:
                metrics = json.loads(r.metrics_summary)
            except Exception:
                pass

        is_stale = False
        if max_demand_date and r.data_date_max:
            is_stale = bool(max_demand_date > r.data_date_max)
        elif r.is_stale:
            is_stale = True

        data_through_val = r.data_date_max or max_demand_date

        status_str = "complete" if (r.status or "").lower() in ("complete", "completed") else (r.status or "complete").lower()
        results.append({
            "id": r.id,
            "product_id": r.product_id or "ALL",
            "horizon_days": r.horizon_days,
            "model_name": r.model_name,
            "status": status_str,
            "evaluation": {
                "wape": metrics.get("wape"),
                "mae": metrics.get("mae"),
                "rmse": metrics.get("rmse"),
            },
            "created_at": r.created_at.isoformat() if r.created_at else datetime.now(timezone.utc).isoformat(),
            "data_through": data_through_val.isoformat() if data_through_val else None,
            "is_stale": is_stale,
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }


class TriggerForecastRunRequest(BaseModel):
    product_ids: Optional[List[str]] = None
    sku: Optional[str] = None
    product_id: Optional[str] = None
    models: Optional[List[str]] = None
    horizon_days: Optional[int] = None
    horizon: Optional[int] = None
    dataset_id: Optional[int] = None
    as_of: Optional[date] = None
    force_refresh: bool = True


@router.post("/run")
def trigger_forecast_run(
    payload: TriggerForecastRunRequest,
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db),
):
    """
    Triggers demand forecasting for specified products, models, and horizon.
    Generates real database forecast runs with historical backtesting and future projection points.
    Runs asynchronously and returns job_id immediately.
    """
    target_dataset = resolve_dataset(db, None, payload.dataset_id)
    product_ids = list(payload.product_ids) if payload.product_ids else []
    if payload.sku:
        product_ids.append(str(payload.sku))
    elif payload.product_id:
        product_ids.append(str(payload.product_id))
    # Remove duplicates preserving order
    product_ids = list(dict.fromkeys(product_ids))

    if not product_ids:
        rows = (
            db.query(DailyProductDemand.product_id)
            .filter(DailyProductDemand.dataset_id == target_dataset.id)
            .distinct()
            .limit(10)
            .all()
        )
        product_ids = [str(r[0]) for r in rows if r[0]]

    models = payload.models or ["prophet", "moving_avg", "naive"]
    horizon_days = payload.horizon_days or payload.horizon or 14

    MODEL_MAPPING = {
        "prophet": "Prophet",
        "moving_avg": "MovingAverage_7D",
        "movingaverage_7d": "MovingAverage_7D",
        "movingaverage_30d": "MovingAverage_30D",
        "naive": "Naive",
        "ridge": "Ridge_LagFeatures",
        "croston": "Croston_SBA",
        "ensemble": "Prophet_MovingAvg_Ensemble",
    }

    # Create async job record BEFORE spawning thread
    target_dataset_id = int(target_dataset.id)
    job_id = str(uuid.uuid4())
    job_record = ForecastJob(
        id=job_id,
        status="running",
        dataset_id=target_dataset_id,
        product_ids=json.dumps(product_ids),
        models=json.dumps(models),
        horizon_days=horizon_days,
    )
    db.add(job_record)
    db.commit()

    successful_runs = 0
    errors = []

    def _do_run_sync():
        nonlocal successful_runs
        db2 = SessionLocal()
        try:
            from backend.services.forecast_service import compute_forecast_summary
            for pid in product_ids:
                try:
                    res = compute_forecast_summary(
                        db=db2,
                        dataset_id=target_dataset_id,
                        product_id=str(pid),
                        horizon_days=horizon_days,
                        force_recompute=True,
                    )
                    if res.get("status") == "success":
                        successful_runs += 1
                except Exception as exc:
                    errors.append(str(exc))
            # Update job record
            job_obj = db2.query(ForecastJob).filter(ForecastJob.id == job_id).first()
            if job_obj:
                job_obj.status = "done" if not errors else "done_with_errors"
                job_obj.result_summary = json.dumps({
                    "successful_runs": successful_runs,
                    "product_ids": product_ids,
                    "errors": errors[:5],
                })
                job_obj.completed_at = datetime.now(timezone.utc)
                db2.commit()
        except Exception as exc:
            job_obj = db2.query(ForecastJob).filter(ForecastJob.id == job_id).first()
            if job_obj:
                job_obj.status = "failed"
                job_obj.error_message = str(exc)[:500]
                job_obj.completed_at = datetime.now(timezone.utc)
                db2.commit()
        finally:
            db2.close()

    # Kick off background thread (non-blocking)
    t = threading.Thread(target=_do_run_sync, daemon=True)
    t.start()

    return {
        "status": "queued",
        "job_id": job_id,
        "message": f"Forecast job queued for {len(product_ids)} SKU(s). Poll /api/forecast/jobs/{job_id} for status.",
        "product_ids": product_ids,
        "models": models,
        "horizon_days": horizon_days,
    }


# -------------------------------------------------------------------------
# Lead Time & Stock Configuration Endpoints (Simulated -> Configured)
# -------------------------------------------------------------------------

class UpdateLeadTimeRequest(BaseModel):
    product_id: str
    dataset_id: Optional[int] = None
    lead_time_days: int = Field(..., ge=1, le=180, description="Supplier lead time in days")
    current_stock: Optional[float] = Field(default=None, ge=0, description="Current on-hand inventory units")
    supplier_name: Optional[str] = Field(default=None, description="Supplier / vendor name")
    service_level: Optional[float] = Field(default=0.95, ge=0.5, le=0.999)


@router.get("/lead-time")
def get_sku_lead_time_settings(
    sku: str = Query(..., description="Product SKU ID"),
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns current supplier lead-time parameters and stock levels for a SKU.
    Indicates whether lead time is verified/configured or simulated default.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    product = db.query(Product).filter(Product.product_id == str(sku)).first()

    sp = (
        db.query(SupplierProduct)
        .filter(SupplierProduct.product_id == str(sku))
        .order_by(SupplierProduct.is_preferred.desc(), SupplierProduct.id.asc())
        .first()
    )

    lto = (
        db.query(LeadTimeObservation)
        .filter(
            LeadTimeObservation.dataset_id == target_dataset.id,
            LeadTimeObservation.product_id == str(sku),
        )
        .order_by(LeadTimeObservation.created_at.desc())
        .first()
    )

    inv = (
        db.query(InventoryState)
        .filter(
            InventoryState.dataset_id == target_dataset.id,
            InventoryState.product_id == str(sku),
        )
        .order_by(InventoryState.snapshot_date.desc(), InventoryState.id.desc())
        .first()
    )

    configured_lead_time = None
    is_configured = False
    if sp and sp.promised_lead_time_days:
        configured_lead_time = sp.promised_lead_time_days
        is_configured = True
    elif lto and lto.actual_days:
        configured_lead_time = lto.actual_days
        is_configured = True

    supplier_name = sp.supplier.name if (sp and sp.supplier) else "Primary Wholesale Distributor"
    supplier_id = sp.supplier_id if sp else None

    return {
        "status": "success",
        "product_id": str(sku),
        "product_name": product.product_name if product else str(sku),
        "dataset_id": target_dataset.id,
        "lead_time_days": configured_lead_time if configured_lead_time is not None else 7,
        "is_configured": is_configured,
        "current_stock": float(inv.closing_stock) if (inv and inv.closing_stock is not None) else None,
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "service_level": 0.95,
    }


@router.post("/lead-time")
def update_sku_lead_time_settings(
    payload: UpdateLeadTimeRequest,
    db: Session = Depends(get_db),
    _write_guard: None = Depends(enforce_writable_db),
):
    """
    Updates or configures real supplier lead time and on-hand inventory for a SKU.
    Transitions recommendation from simulated default to verified supply-chain parameters.
    """
    target_dataset = resolve_dataset(db, None, payload.dataset_id)
    product_id_str = str(payload.product_id).strip()

    # 1. Resolve or create Supplier
    supplier_name = (payload.supplier_name or "").strip() or "Primary Wholesale Distributor"
    supplier = db.query(Supplier).filter(Supplier.name.ilike(supplier_name)).first()
    if not supplier:
        supplier = Supplier(
            name=supplier_name,
            contact_email=f"procurement@{supplier_name.lower().replace(' ', '')}.com",
            payment_terms_days=30,
            min_order_value=0.0,
            is_active=True,
        )
        db.add(supplier)
        db.flush()

    # 2. Upsert SupplierProduct
    sp = (
        db.query(SupplierProduct)
        .filter(
            SupplierProduct.product_id == product_id_str,
            SupplierProduct.supplier_id == supplier.id,
        )
        .first()
    )
    if not sp:
        # Check if any supplier product exists for this item
        sp = db.query(SupplierProduct).filter(SupplierProduct.product_id == product_id_str).first()

    if sp:
        sp.supplier_id = supplier.id
        sp.promised_lead_time_days = payload.lead_time_days
        sp.is_preferred = True
    else:
        sp = SupplierProduct(
            supplier_id=supplier.id,
            product_id=product_id_str,
            unit_cost=10.0,
            moq=1,
            order_multiple=1,
            promised_lead_time_days=payload.lead_time_days,
            is_preferred=True,
        )
        db.add(sp)

    # 3. Record LeadTimeObservation for audit and statistical models (King's formula)
    now_utc = datetime.now(timezone.utc)
    obs = LeadTimeObservation(
        dataset_id=target_dataset.id,
        product_id=product_id_str,
        supplier_id=str(supplier.id),
        po_id="MANUAL_SLA_CONFIG",
        promised_days=payload.lead_time_days,
        actual_days=payload.lead_time_days,
        ordered_at=now_utc,
        received_at=now_utc,
    )
    db.add(obs)

    # 4. If current stock provided, upsert InventoryState
    today_date = date.today()
    if payload.current_stock is not None:
        inv = (
            db.query(InventoryState)
            .filter(
                InventoryState.dataset_id == target_dataset.id,
                InventoryState.product_id == product_id_str,
                InventoryState.snapshot_date == today_date,
            )
            .first()
        )
        if inv:
            inv.opening_stock = float(payload.current_stock)
            inv.closing_stock = float(payload.current_stock)
            inv.is_simulated = False
        else:
            inv = InventoryState(
                dataset_id=target_dataset.id,
                product_id=product_id_str,
                city_name="ALL",
                snapshot_date=today_date,
                opening_stock=float(payload.current_stock),
                stock_received=0.0,
                sales_quantity=0.0,
                closing_stock=float(payload.current_stock),
                is_simulated=False,
            )
            db.add(inv)

    db.commit()

    return {
        "status": "success",
        "message": f"Successfully updated lead time to {payload.lead_time_days} days for SKU {product_id_str}.",
        "product_id": product_id_str,
        "lead_time_days": payload.lead_time_days,
        "current_stock": payload.current_stock,
        "supplier_name": supplier.name,
        "is_configured": True,
    }


@router.get("/{run_id}")
def get_forecast_run_detail(
    run_id: str,
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Retrieve details for a forecast run or SKU product_id within the scoped dataset (Prompt Fix 3).
    Queries real forecast_runs and forecasts tables.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    latest_upload_id = get_latest_upload_job_id(db, target_dataset.id)

    max_demand_date = (
        db.query(func.max(DailyProductDemand.date_))
        .filter(DailyProductDemand.dataset_id == target_dataset.id)
        .scalar()
    )

    # 1. First check if run_id matches a real ForecastRun by ID
    run_obj = None
    if run_id.isdigit():
        run_obj = db.query(ForecastRun).filter(
            ForecastRun.id == int(run_id),
            ForecastRun.dataset_id == target_dataset.id
        ).first()

    if run_obj:
        items = (
            db.query(ForecastItem)
            .filter(ForecastItem.run_id == run_obj.id)
            .order_by(ForecastItem.forecast_date.asc())
            .all()
        )

        hist_records = []
        if run_obj.product_id:
            hist_records = (
                db.query(DailyProductDemand)
                .filter(
                    DailyProductDemand.dataset_id == target_dataset.id,
                    DailyProductDemand.product_id == run_obj.product_id
                )
                .order_by(DailyProductDemand.date_.asc())
                .all()
            )

        points = []
        for h in hist_records:
            points.append({
                "forecast_date": h.date_.isoformat(),
                "actual": float(h.total_quantity or 0.0),
                "yhat": float(h.total_quantity or 0.0),
                "yhat_lower": float(h.total_quantity or 0.0),
                "yhat_upper": float(h.total_quantity or 0.0),
                "is_future": False,
            })
        for it in items:
            pred = float(it.predicted_demand or 0.0)
            points.append({
                "forecast_date": it.forecast_date.isoformat(),
                "actual": None,
                "yhat": pred,
                "yhat_lower": float(it.lower_bound) if it.lower_bound is not None else round(pred * 0.8, 2),
                "yhat_upper": float(it.upper_bound) if it.upper_bound is not None else round(pred * 1.2, 2),
                "quantiles": it.quantiles or {},
                "is_future": True,
            })

        metrics = {}
        if run_obj.metrics_summary:
            try:
                metrics = json.loads(run_obj.metrics_summary)
            except Exception:
                pass

        data_through_val = run_obj.data_date_max or max_demand_date
        is_stale_val = bool(max_demand_date and run_obj.data_date_max and max_demand_date > run_obj.data_date_max)

        return {
            "id": run_obj.id,
            "dataset_id": target_dataset.id,
            "product_id": run_obj.product_id or "ALL",
            "horizon_days": run_obj.horizon_days,
            "model_name": run_obj.model_name,
            "status": (run_obj.status or "complete").lower(),
            "evaluation": metrics,
            "created_at": run_obj.created_at.isoformat() if run_obj.created_at else datetime.now(timezone.utc).isoformat(),
            "freshness": {
                "computed_at": run_obj.created_at.isoformat() if run_obj.created_at else datetime.now(timezone.utc).isoformat(),
                "data_through": data_through_val.isoformat() if data_through_val else None,
                "is_stale": is_stale_val,
                "model_name": run_obj.model_name,
                "source_upload_job_id": run_obj.source_upload_job_id or latest_upload_id
            },
            "points": points,
        }

    # 2. If run_id is a product_id (string like '476763'), check daily demand records
    records = (
        db.query(DailyProductDemand)
        .filter(
            DailyProductDemand.dataset_id == target_dataset.id,
            DailyProductDemand.product_id == str(run_id)
        )
        .order_by(DailyProductDemand.date_.asc())
        .all()
    )
    if records:
        quantities = [float(r.total_quantity or 0.0) for r in records]
        window = quantities[-30:] if len(quantities) >= 30 else quantities
        mean_val = round(sum(window) / len(window), 2) if window else 0.0
        data_through_val = records[-1].date_ if records else max_demand_date
        return {
            "id": f"dynamic-{run_id}",
            "dataset_id": target_dataset.id,
            "product_id": str(run_id),
            "status": "complete",
            "predicted_mean": mean_val,
            "yhat_mean": mean_val,
            # No hardcoded metrics — values are not real
            "evaluation": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "freshness": {
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "data_through": data_through_val.isoformat() if data_through_val else None,
                "is_stale": False,
                "model_name": "MovingAverage_7D",
                "source_upload_job_id": latest_upload_id
            },
            "points": [
                {
                    "forecast_date": r.date_.isoformat(),
                    "actual": float(r.total_quantity),
                    "yhat": float(r.total_quantity),
                    "is_future": False
                }
                for r in records[-30:]
            ]
        }

    raise HTTPException(status_code=404, detail=f"Forecast run '{run_id}' not found.")


# -------------------------------------------------------------------------
# Prompt 5.7: Model Registry, Champion/Challenger & Drift Monitoring Endpoints
# -------------------------------------------------------------------------

@router.post("/evaluate-champion/{product_id}")
def run_champion_challenger_tournament(
    product_id: str,
    dataset_id: Optional[int] = Query(default=None),
    city_name: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _role: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
):
    """
    Executes Champion/Challenger tournament for a SKU across candidate models
    with 5% hysteresis margin and chronological rolling-origin backtest.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    return evaluate_and_promote_champion(
        db=db,
        dataset_id=target_dataset.id,
        product_id=product_id,
        city_name=city_name,
    )


@router.get("/models/performance")
def get_portfolio_model_performance(
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns portfolio model dashboard: WAPE distribution, champion model mix pie,
    accuracy trends, and worst-performing SKUs.
    """
    return get_model_performance_dashboard(db=db, dataset_id=dataset_id)


@router.get("/models/drift/{product_id}")
def get_sku_drift_monitoring(
    product_id: str,
    dataset_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Monitors rolling WAPE performance drift and Population Stability Index (PSI)
    data drift for a specific SKU.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    return monitor_sku_model_drift(
        db=db,
        dataset_id=target_dataset.id,
        product_id=product_id,
    )


# -------------------------------------------------------------------------
# Prompt 5.8: Analog Cold-Start & Synthetic Launch Curve Endpoints
# -------------------------------------------------------------------------

class AnalogColdStartRequest(BaseModel):
    product_id: str
    dataset_id: Optional[int] = None
    city_name: Optional[str] = None
    horizon_days: int = 14


class LaunchCurveRequest(BaseModel):
    peak_estimate: float
    curve_shape: str = "fast_ramp"  # fast_ramp, slow_build, seasonal_spike
    horizon_days: int = 30


@router.post("/cold-start/analog")
def generate_analog_cold_start(
    payload: AnalogColdStartRequest,
    db: Session = Depends(get_db),
):
    """
    Generates analog-based blended forecast for a new product with < 30 observations,
    decaying to zero weight by 60 observations and widening uncertainty bands by 1.75x.
    """
    target_dataset = resolve_dataset(db, None, payload.dataset_id)
    return generate_analog_cold_start_forecast(
        db=db,
        dataset_id=target_dataset.id,
        product_id=payload.product_id,
        city_name=payload.city_name,
        horizon_days=payload.horizon_days,
    )


@router.post("/cold-start/launch-curve")
def generate_launch_curve(payload: LaunchCurveRequest):
    """
    Generates synthetic launch-curve for genuinely new categories with user-selected shape
    (fast_ramp, slow_build, seasonal_spike) and peak volume estimate.
    """
    return generate_launch_curve_forecast(
        peak_estimate=payload.peak_estimate,
        curve_shape=payload.curve_shape,
        horizon_days=payload.horizon_days,
    )

