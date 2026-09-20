"""
Inventory Optimization Service with King's Safety Stock Formula & Lead-Time Variability
Project: Demand-Decision-Intelligence
"""

import math
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.demand import DailyProductDemand
from backend.models.inventory import LeadTimeObservation, InventoryRecommendation
from backend.models.upload import UploadJob
from backend.models.dataset import Dataset
from backend.services.forecast_service import check_historical_warning
from datetime import date, datetime, timezone


def compute_safety_stock_kings(
    avg_demand: float,
    std_demand: float,
    lead_time_days: float,
    std_lead_time: float,
    z_score: float = 1.645
) -> float:
    """
    Computes Safety Stock using King's Formula accounting for both demand variability
    and lead-time variability:

        SS = Z * sqrt( L * sigma_d^2  +  d_bar^2 * sigma_L^2 )

    References:
        King, P. L. (2011). Crack the Code: Understanding Safety Stock and Mastering its Formulas.
        APICS Magazine, July/August 2011.

    Key Assumptions:
        1. Daily customer demand and replenishment lead time are mutually independent random variables.
        2. Demand across days within the replenishment cycle is independent and identically distributed (i.i.d.).
        3. When sigma_L == 0 (deterministic/constant lead time), King's formula reduces exactly to the
           classical formula: SS = Z * sigma_d * sqrt(L).
    """
    variance_term = (lead_time_days * (std_demand ** 2)) + ((avg_demand ** 2) * (std_lead_time ** 2))
    return round(z_score * math.sqrt(max(0.0, variance_term)), 2)


def compute_safety_stock_classical(
    std_demand: float,
    lead_time_days: float,
    z_score: float = 1.645
) -> float:
    """
    Classical constant lead-time safety stock formula:
        SS = ceil(Z * sigma_d * sqrt(L))
    """
    return float(math.ceil(z_score * std_demand * math.sqrt(max(0.0, lead_time_days))))


def get_lead_time_stats(
    db: Session,
    dataset_id: int,
    product_id: str,
    supplier_id: Optional[str] = None,
    default_lead_time: float = 7.0,
    default_cv: float = 0.25,
) -> Dict[str, Any]:
    """
    Calculates lead time statistics from lead_time_observations table.
    Requires at least 5 observations; below that, falls back to default CV of lead time (0.25 * L)
    and labels confidence as LOW.
    """
    query = db.query(LeadTimeObservation).filter(
        LeadTimeObservation.dataset_id == dataset_id,
        LeadTimeObservation.product_id == str(product_id),
    )
    if supplier_id:
        query = query.filter(LeadTimeObservation.supplier_id == str(supplier_id))

    observations = query.all()
    n_obs = len(observations)

    if n_obs >= 5:
        actuals = [float(o.actual_days) for o in observations]
        mean_l = sum(actuals) / n_obs
        variance_l = sum((x - mean_l) ** 2 for x in actuals) / (n_obs - 1) if n_obs > 1 else 0.0
        sigma_l = math.sqrt(variance_l)
        return {
            "lead_time_days": round(mean_l, 2),
            "lead_time_sd": round(sigma_l, 2),
            "observations_count": n_obs,
            "confidence": "HIGH",
            "is_fallback": False,
        }
    else:
        # Fallback to default CV of lead time (0.25 * L)
        mean_l = default_lead_time
        if n_obs > 0:
            mean_l = sum(float(o.actual_days) for o in observations) / n_obs
        sigma_l = default_cv * mean_l
        return {
            "lead_time_days": round(mean_l, 2),
            "lead_time_sd": round(sigma_l, 2),
            "observations_count": n_obs,
            "confidence": "LOW",
            "is_fallback": True,
        }


def compute_inventory_recommendation_for_sku(
    db: Session,
    target_dataset: Dataset,
    product_id: str,
    city_name: Optional[str] = None,
    supplier_id: Optional[str] = None,
    as_of: Optional[date] = None,
    use_classical: bool = False,
    service_level: float = 0.95,
) -> Optional[Dict[str, Any]]:
    """
    Computes comprehensive inventory recommendation for a SKU using King's formula,
    providing both King's and classical safety stock values, delta, and lead-time variability metrics.
    """
    query = db.query(DailyProductDemand).filter(
        DailyProductDemand.dataset_id == target_dataset.id,
        DailyProductDemand.product_id == str(product_id),
    )
    if as_of:
        query = query.filter(DailyProductDemand.date_ <= as_of)
    if city_name and city_name != "ALL":
        query = query.filter(DailyProductDemand.city_name == city_name)

    records = query.order_by(DailyProductDemand.date_.asc()).all()
    if not records:
        return None

    quantities = [float(r.total_quantity or 0.0) for r in records]
    avg_demand = sum(quantities) / len(quantities) if quantities else 0.0
    variance = sum((q - avg_demand) ** 2 for q in quantities) / len(quantities) if quantities else 0.0
    std_demand = math.sqrt(variance)

    # Lead time variability
    lt_stats = get_lead_time_stats(db, target_dataset.id, product_id, supplier_id)
    lead_time_days = lt_stats["lead_time_days"]
    sigma_l = lt_stats["lead_time_sd"]

    z_score = 1.645 if service_level >= 0.95 else 1.28

    ss_kings = compute_safety_stock_kings(avg_demand, std_demand, lead_time_days, sigma_l, z_score)
    ss_classical = compute_safety_stock_classical(std_demand, lead_time_days, z_score)
    ss_delta = round(ss_kings - ss_classical, 2)

    active_ss = ss_classical if use_classical else ss_kings
    reorder_point = round((avg_demand * lead_time_days) + active_ss, 2)
    target_stock = round(reorder_point + (avg_demand * lead_time_days), 2)

    avg_price = records[-1].avg_unit_price if records[-1].avg_unit_price else 10.0
    unit_landing_cost = round(avg_price * 0.8, 2)

    effective_as_of = as_of or records[-1].date_
    hist_warn = check_historical_warning(effective_as_of)

    return {
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "product_id": str(product_id),
        "city_name": city_name or (records[0].city_name if records else "ALL"),
        "mean_daily_demand": round(avg_demand, 2),
        "std_daily_demand": round(std_demand, 2),
        "lead_time_days": lead_time_days,
        "lead_time_sd": sigma_l,
        "lead_time_confidence": lt_stats["confidence"],
        "lead_time_observations_count": lt_stats["observations_count"],
        "service_level": service_level,
        "safety_stock": active_ss,
        "safety_stock_kings": ss_kings,
        "safety_stock_classical": ss_classical,
        "safety_stock_delta": ss_delta,
        "formula_used": "classical" if use_classical else "kings",
        "reorder_point": reorder_point,
        "target_stock_level": target_stock,
        "unit_landing_cost": unit_landing_cost,
        "stockout_risk_score": 0.05 if active_ss > 0 else 0.5,
        "recommendation": "REORDER" if active_ss > 0 else "MAINTAIN",
        "as_of": effective_as_of.isoformat(),
        "historical_warning": hist_warn,
    }
