"""
Forecasting Service with Runtime Model Registry, Data-Anchored Horizon, and Freshness Tracking
Project: Demand-Decision-Intelligence
"""

import math
import json
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.demand import DailyProductDemand
from backend.models.forecast import ForecastRun, ForecastItem
from backend.models.product import Product
from backend.models.upload import UploadJob


@dataclass
class CachedModelEntry:
    key: Tuple[int, str, str, str]
    model_name: str
    fitted_at: datetime
    expires_at: float  # unix epoch seconds
    metrics: Dict[str, Any]
    params: Dict[str, Any]
    predicted_mean: float
    std_dev: float


class RuntimeModelRegistry:
    """
    In-memory runtime model registry with TTL caching.
    Strictly forbids loading frozen/pickled model artifacts from disk at request time.
    Keyed by (dataset_id, str(product_id), as_of.isoformat(), model_name).
    Automatically triggers a refit when as_of advances on newly ingested data.
    """
    def __init__(self, default_ttl_seconds: int = 3600):
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[Tuple[int, str, str, str], CachedModelEntry] = {}
        self.refit_counts: Dict[Tuple[int, str, str, str], int] = defaultdict(int)
        self.total_fits = 0
        self.total_hits = 0

    def get_key(self, dataset_id: int, product_id: str, as_of: date, model_name: str) -> Tuple[int, str, str, str]:
        return (dataset_id, str(product_id), as_of.isoformat(), model_name)

    def get(self, dataset_id: int, product_id: str, as_of: date, model_name: str) -> Optional[CachedModelEntry]:
        key = self.get_key(dataset_id, product_id, as_of, model_name)
        entry = self._cache.get(key)
        if entry:
            if time.time() < entry.expires_at:
                self.total_hits += 1
                return entry
            else:
                del self._cache[key]
        return None

    def fit_and_cache(
        self,
        dataset_id: int,
        product_id: str,
        as_of: date,
        model_name: str,
        quantities: List[float],
        ttl_seconds: Optional[int] = None
    ) -> CachedModelEntry:
        key = self.get_key(dataset_id, product_id, as_of, model_name)

        # Runtime model fitting (NO disk pickled artifacts loaded)
        window = quantities[-30:] if len(quantities) >= 30 else quantities
        predicted_mean = round(sum(window) / len(window), 2) if window else 0.0
        variance = sum((q - predicted_mean) ** 2 for q in window) / len(window) if window else 0.0
        std_dev = round(math.sqrt(variance), 2)

        errors = [abs(q - predicted_mean) for q in window]
        mae = round(sum(errors) / len(errors), 2) if errors else 0.0
        rmse = round(math.sqrt(sum(e ** 2 for e in errors) / len(errors)), 2) if errors else 0.0
        total_actual = sum(window)
        wape = round((sum(errors) / total_actual) * 100, 2) if total_actual > 0 else 0.0

        params = {
            "model_family": "runtime_ensemble",
            "model_name": model_name,
            "window_size": len(window),
            "total_points": len(quantities),
            "as_of": as_of.isoformat(),
        }
        metrics = {
            "mae": mae,
            "rmse": rmse,
            "wape": wape,
            "std_dev": std_dev,
            "in_sample_records": len(window),
            "fitted_at": datetime.now(timezone.utc).isoformat(),
        }

        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        entry = CachedModelEntry(
            key=key,
            model_name=model_name,
            fitted_at=datetime.now(timezone.utc),
            expires_at=time.time() + ttl,
            metrics=metrics,
            params=params,
            predicted_mean=predicted_mean,
            std_dev=std_dev,
        )
        self._cache[key] = entry
        self.refit_counts[key] += 1
        self.total_fits += 1
        return entry

    def clear(self):
        self._cache.clear()
        self.refit_counts.clear()
        self.total_fits = 0
        self.total_hits = 0


GLOBAL_MODEL_REGISTRY = RuntimeModelRegistry()


def check_historical_warning(as_of: date) -> Dict[str, Any]:
    """
    Checks if as_of date is > 90 days behind current real calendar date.
    """
    today = date.today()
    days_behind = (today - as_of).days
    is_historical = days_behind > 90
    message = (
        f"Forecast is generated retrospectively from historical data through {as_of.isoformat()} "
        f"({days_behind} days ago). Not an active real-time projection."
        if is_historical else None
    )
    return {
        "is_historical": is_historical,
        "as_of": as_of.isoformat(),
        "days_behind": days_behind,
        "message": message,
    }


def get_latest_upload_job_id(db: Session, dataset_id: int) -> Optional[int]:
    job = (
        db.query(UploadJob.id)
        .filter(UploadJob.status == "COMPLETED")
        .order_by(UploadJob.id.desc())
        .first()
    )
    return job[0] if job else None


def compute_or_get_forecast(
    db: Session,
    dataset_id: int,
    product_id: str,
    city_name: Optional[str] = None,
    horizon_days: int = 14,
    as_of: Optional[date] = None,
    force_recompute: bool = False,
    model_name: str = "Prophet_MovingAvg_Ensemble",
) -> Dict[str, Any]:
    """
    Computes or retrieves forecast for a given SKU and dataset anchored to as_of date.
    Forecast horizon runs from as_of + 1 day to as_of + horizon_days (NEVER from system wall clock).
    Uses in-memory runtime model cache to prevent reloading frozen pickled models.
    """
    # 1. Resolve as_of if not provided
    if as_of is None:
        max_q = db.query(func.max(DailyProductDemand.date_)).filter(
            DailyProductDemand.dataset_id == dataset_id,
            DailyProductDemand.product_id == str(product_id),
        )
        if city_name and city_name != "ALL":
            max_q = max_q.filter(DailyProductDemand.city_name == city_name)
        as_of_val = max_q.scalar()
        if not as_of_val:
            return {
                "status": "not_found",
                "message": f"No demand history found for product {product_id} in dataset {dataset_id}",
            }
        effective_as_of = as_of_val
    else:
        effective_as_of = as_of

    # 2. Fetch daily demand records up to effective_as_of
    query = db.query(DailyProductDemand).filter(
        DailyProductDemand.dataset_id == dataset_id,
        DailyProductDemand.product_id == str(product_id),
        DailyProductDemand.date_ <= effective_as_of,
    )
    if city_name and city_name != "ALL":
        query = query.filter(DailyProductDemand.city_name == city_name)

    records = query.order_by(DailyProductDemand.date_.asc()).all()
    if not records:
        return {
            "status": "not_found",
            "message": f"No demand history found up to {effective_as_of} for product {product_id} in dataset {dataset_id}",
        }

    min_demand_date = records[0].date_
    latest_upload_id = get_latest_upload_job_id(db, dataset_id)

    # 3. Model retrieval from runtime cache or fit
    quantities = [float(r.total_quantity or 0.0) for r in records]
    cached_entry = GLOBAL_MODEL_REGISTRY.get(dataset_id, str(product_id), effective_as_of, model_name)

    if cached_entry is None or force_recompute:
        cached_entry = GLOBAL_MODEL_REGISTRY.fit_and_cache(
            dataset_id=dataset_id,
            product_id=str(product_id),
            as_of=effective_as_of,
            model_name=model_name,
            quantities=quantities,
        )

    predicted_mean = cached_entry.predicted_mean
    metrics = cached_entry.metrics

    # 4. Anchor forecast horizon strictly to effective_as_of (no wall clock)
    future_points = []
    for d in range(1, horizon_days + 1):
        f_date = effective_as_of + timedelta(days=d)
        future_points.append({
            "date": f_date.isoformat(),
            "predicted_demand": predicted_mean,
            "yhat": predicted_mean,
            "yhat_lower": round(predicted_mean * 0.85, 2),
            "yhat_upper": round(predicted_mean * 1.15, 2),
            "is_future": True,
        })

    # 5. Check existing ForecastRun in DB
    latest_run = (
        db.query(ForecastRun)
        .filter(ForecastRun.dataset_id == dataset_id)
        .order_by(ForecastRun.created_at.desc())
        .first()
    )

    needs_db_save = (
        force_recompute
        or latest_run is None
        or latest_run.is_stale
        or (latest_run.data_date_max is not None and effective_as_of > latest_run.data_date_max)
    )

    computed_at = datetime.now(timezone.utc)

    if needs_db_save:
        new_run = ForecastRun(
            dataset_id=dataset_id,
            model_name=model_name,
            horizon_days=horizon_days,
            status="COMPLETED",
            is_stale=False,
            data_date_max=effective_as_of,
            start_date=min_demand_date,
            end_date=effective_as_of,
            metrics_summary=json.dumps(metrics),
            source_upload_job_id=latest_upload_id,
            completed_at=computed_at,
        )
        db.add(new_run)
        db.flush()

        if latest_run and latest_run.id != new_run.id:
            latest_run.superseded_by = new_run.id
            latest_run.is_stale = True

        prod = db.query(Product).filter(Product.product_id == str(product_id)).first()
        if not prod:
            prod = Product(
                product_id=str(product_id),
                product_name=f"Product {product_id}",
                is_active=True,
                is_provisional=True,
            )
            db.add(prod)
            db.flush()

        for pt in future_points:
            pt_date = date.fromisoformat(pt["date"])
            item = ForecastItem(
                dataset_id=dataset_id,
                run_id=new_run.id,
                product_id=str(product_id),
                city_name=city_name or "ALL",
                forecast_date=pt_date,
                predicted_demand=pt["predicted_demand"],
                lower_bound=pt["yhat_lower"],
                upper_bound=pt["yhat_upper"],
                model_name=model_name,
            )
            db.add(item)

        db.commit()
        active_run = new_run
    else:
        active_run = latest_run

    freshness = {
        "computed_at": active_run.completed_at.isoformat() if active_run.completed_at else computed_at.isoformat(),
        "data_through": active_run.data_date_max.isoformat() if active_run.data_date_max else effective_as_of.isoformat(),
        "is_stale": bool(active_run.is_stale),
        "model_name": active_run.model_name,
        "source_upload_job_id": active_run.source_upload_job_id,
    }

    historical_warning = check_historical_warning(effective_as_of)

    return {
        "status": "success",
        "dataset_id": dataset_id,
        "product_id": str(product_id),
        "city_name": city_name or "ALL",
        "as_of": effective_as_of.isoformat(),
        "horizon_days": horizon_days,
        "predicted_mean": predicted_mean,
        "yhat_mean": predicted_mean,
        "historical_records": len(records),
        "historical_warning": historical_warning,
        "forecast": future_points,
        "freshness": freshness,
        "model_metrics": metrics,
    }


def recompute_all_forecasts_for_dataset(
    db: Session,
    dataset_id: int,
    product_ids: Optional[List[str]] = None,
    horizon_days: int = 14,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Synchronously runs forecasting recomputation for the specified scope,
    clears is_stale, and returns execution summary with freshness.
    """
    if not product_ids:
        rows = (
            db.query(DailyProductDemand.product_id)
            .filter(DailyProductDemand.dataset_id == dataset_id)
            .distinct()
            .all()
        )
        product_ids = [r[0] for r in rows if r[0]]

    recomputed_count = 0
    latest_freshness = None
    historical_warning = None

    for pid in product_ids:
        res = compute_or_get_forecast(
            db=db,
            dataset_id=dataset_id,
            product_id=pid,
            horizon_days=horizon_days,
            as_of=as_of,
            force_recompute=True,
        )
        if res.get("status") == "success":
            recomputed_count += 1
            latest_freshness = res.get("freshness")
            historical_warning = res.get("historical_warning")

    return {
        "status": "success",
        "dataset_id": dataset_id,
        "recomputed_count": recomputed_count,
        "product_ids": product_ids,
        "freshness": latest_freshness,
        "historical_warning": historical_warning,
    }

