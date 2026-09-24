"""
backend/services/classification_service.py
-------------------------------------------
Service for ABC-XYZ segmentation and configurable cell policy management (Prompt 4.7).

1. ABC Pareto Segmentation by Annual Consumption Value (quantity * unit_cost):
   - A = top 80% cumulative value
   - B = next 15% (80% to 95%)
   - C = last 5% (95% to 100%)
   (Cutoffs are configurable)

2. XYZ Demand Predictability Segmentation by CV^2:
   - X = CV^2 < 0.25 (stable)
   - Y = 0.25 <= CV^2 <= 1.0 (variable)
   - Z = CV^2 > 1.0 (erratic / intermittent)

3. 9-Cell Policy Differentiation:
   - Integrates with abc_xyz_policies table to provide tunable policies per cell.
"""

import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.classification import ProductClassification, AbcXyzPolicy
from backend.models.demand import DailyProductDemand
from backend.models.product import Product
from backend.models.procurement import SupplierProduct
from backend.services.dataset_service import resolve_dataset


def run_abc_xyz_classification(
    db: Session,
    dataset_id: Optional[int] = None,
    a_cut: float = 0.80,
    b_cut: float = 0.95,
    x_cut: float = 0.25,
    y_cut: float = 1.00,
) -> Dict[str, Any]:
    """
    Computes and stores ABC-XYZ classification for all SKUs in a dataset.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    # 1. Fetch supplier products for unit costs
    preferred_suppliers = {
        sp.product_id: sp
        for sp in db.query(SupplierProduct).filter(SupplierProduct.is_preferred == True).all()
    }
    all_suppliers = {
        sp.product_id: sp
        for sp in db.query(SupplierProduct).all()
    }

    # 2. Aggregate demand metrics from DailyProductDemand
    agg_rows = db.query(
        DailyProductDemand.product_id,
        func.avg(DailyProductDemand.total_quantity).label("mean_qty"),
        func.stddev(DailyProductDemand.total_quantity).label("std_qty"),
        func.avg(DailyProductDemand.avg_unit_price).label("avg_price"),
        func.count(DailyProductDemand.id).label("n_days")
    ).filter(
        DailyProductDemand.dataset_id == target_dataset.id
    ).group_by(
        DailyProductDemand.product_id
    ).all()

    if not agg_rows:
        # Fallback to products table if no demand records exist
        all_prods = db.query(Product).all()
        sku_metrics = []
        for p in all_prods:
            sku_metrics.append({
                "product_id": p.product_id,
                "mean_qty": 5.0,
                "std_qty": 2.0,
                "unit_cost": 25.0,
                "annual_value": 5.0 * 365.0 * 25.0,
                "cv2": (2.0 / 5.0) ** 2,
            })
    else:
        sku_metrics = []
        for r in agg_rows:
            prod_id = str(r.product_id)
            mean_q = float(r.mean_qty or 1.0)
            std_q = float(r.std_qty or 0.35 * mean_q)
            avg_p = float(r.avg_price or 50.0)

            sp = preferred_suppliers.get(prod_id) or all_suppliers.get(prod_id)
            unit_cost = float(sp.unit_cost) if sp and sp.unit_cost > 0 else round(avg_p * 0.75, 2)

            annual_val = round(mean_q * 365.0 * unit_cost, 2)
            cv = (std_q / mean_q) if mean_q > 0 else 0.0
            cv2 = round(cv ** 2, 4)

            sku_metrics.append({
                "product_id": prod_id,
                "mean_qty": round(mean_q, 2),
                "std_qty": round(std_q, 2),
                "unit_cost": unit_cost,
                "annual_value": annual_val,
                "cv2": cv2,
            })

    # 3. Sort by annual consumption value descending for Pareto ABC cuts
    sku_metrics.sort(key=lambda x: x["annual_value"], reverse=True)
    total_val = sum(x["annual_value"] for x in sku_metrics) or 1.0

    # 4. Assign ABC & XYZ
    cum_val = 0.0
    now_ts = datetime.now(timezone.utc)

    # Clear existing classifications for this dataset
    db.query(ProductClassification).filter(
        ProductClassification.dataset_id == target_dataset.id
    ).delete()

    new_records = []
    for item in sku_metrics:
        val = item["annual_value"]
        # Determine ABC
        # Item belongs to A if cumulative value before this item was < a_cut
        cum_share_before = cum_val / total_val
        cum_val += val
        cum_share_after = cum_val / total_val

        if cum_share_before < a_cut:
            abc = "A"
        elif cum_share_before < b_cut:
            abc = "B"
        else:
            abc = "C"

        # Determine XYZ
        cv2_val = item["cv2"]
        if cv2_val < x_cut:
            xyz = "X"
        elif cv2_val <= y_cut:
            xyz = "Y"
        else:
            xyz = "Z"

        cell = f"{abc}{xyz}"

        rec = ProductClassification(
            dataset_id=target_dataset.id,
            product_id=item["product_id"],
            abc_class=abc,
            xyz_class=xyz,
            cell=cell,
            annual_consumption_value=val,
            value_share_cumulative=round(cum_share_after, 4),
            cv2=cv2_val,
            mean_daily_demand=item["mean_qty"],
            std_daily_demand=item["std_qty"],
            unit_cost=item["unit_cost"],
            computed_at=now_ts,
        )
        new_records.append(rec)

    db.bulk_save_objects(new_records)
    db.commit()

    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "total_skus_classified": len(new_records),
        "total_annual_value": round(total_val, 2),
        "cuts": {
            "a_cut": a_cut,
            "b_cut": b_cut,
            "x_cut": x_cut,
            "y_cut": y_cut,
        },
        "computed_at": now_ts.isoformat(),
    }


def get_abc_xyz_matrix(
    db: Session,
    dataset_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Returns 3x3 interactive matrix with cell stats and policy associations.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)

    # Check if classifications exist; if not, run initial classification
    existing_count = db.query(ProductClassification).filter(
        ProductClassification.dataset_id == target_dataset.id
    ).count()

    if existing_count == 0:
        run_abc_xyz_classification(db, dataset_id=target_dataset.id)

    # Fetch all cell policies from database
    policies = {p.cell: p for p in db.query(AbcXyzPolicy).all()}

    # Aggregate counts and values per cell
    cell_aggs = db.query(
        ProductClassification.cell,
        func.count(ProductClassification.id).label("sku_count"),
        func.sum(ProductClassification.annual_consumption_value).label("total_value")
    ).filter(
        ProductClassification.dataset_id == target_dataset.id
    ).group_by(
        ProductClassification.cell
    ).all()

    agg_map = {row.cell: (row.sku_count, float(row.total_value or 0.0)) for row in cell_aggs}

    total_catalog_value = sum(v[1] for v in agg_map.values()) or 1.0
    total_skus = sum(v[0] for v in agg_map.values())

    cells_order = [
        "AX", "AY", "AZ",
        "BX", "BY", "BZ",
        "CX", "CY", "CZ"
    ]

    matrix_cells = []
    for cell_code in cells_order:
        abc = cell_code[0]
        xyz = cell_code[1]
        count, val = agg_map.get(cell_code, (0, 0.0))
        val_pct = round((val / total_catalog_value) * 100.0, 1)
        pol = policies.get(cell_code)

        matrix_cells.append({
            "cell": cell_code,
            "abc_class": abc,
            "xyz_class": xyz,
            "sku_count": count,
            "sku_percentage": round((count / total_skus * 100.0), 1) if total_skus > 0 else 0.0,
            "annual_consumption_value": round(val, 2),
            "value_percentage": val_pct,
            "policy": {
                "review_strategy": pol.review_strategy if pol else "CONTINUOUS",
                "target_service_level": pol.target_service_level if pol else 0.95,
                "safety_stock_policy": pol.safety_stock_policy if pol else "STANDARD_KINGS",
                "reorder_automation": pol.reorder_automation if pol else "AUTOMATED",
                "review_frequency_days": pol.review_frequency_days if pol else 1,
                "description": pol.description if pol else "",
            } if pol else None
        })

    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "total_skus": total_skus,
        "total_annual_value": round(total_catalog_value, 2),
        "cells": matrix_cells,
        "grid": {
            "A": [c for c in matrix_cells if c["abc_class"] == "A"],
            "B": [c for c in matrix_cells if c["abc_class"] == "B"],
            "C": [c for c in matrix_cells if c["abc_class"] == "C"],
        }
    }


def get_skus_for_cell(
    db: Session,
    dataset_id: Optional[int] = None,
    cell: str = "AX",
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Returns drilled-down SKU details for a specific ABC-XYZ cell.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    cell = cell.upper()

    query = db.query(
        ProductClassification,
        Product.product_name,
        Product.brand_name,
        Product.l0_category
    ).outerjoin(
        Product, Product.product_id == ProductClassification.product_id
    ).filter(
        ProductClassification.dataset_id == target_dataset.id,
        ProductClassification.cell == cell
    )

    total = query.count()
    rows = query.order_by(ProductClassification.annual_consumption_value.desc()).offset(offset).limit(limit).all()

    policy = db.query(AbcXyzPolicy).filter(AbcXyzPolicy.cell == cell).first()

    items = []
    for pc, p_name, brand, cat in rows:
        items.append({
            "product_id": pc.product_id,
            "product_name": p_name or f"SKU #{pc.product_id}",
            "brand_name": brand or "Generic",
            "category": cat or "General",
            "cell": pc.cell,
            "abc_class": pc.abc_class,
            "xyz_class": pc.xyz_class,
            "annual_consumption_value": pc.annual_consumption_value,
            "cv2": pc.cv2,
            "mean_daily_demand": pc.mean_daily_demand,
            "std_daily_demand": pc.std_daily_demand,
            "unit_cost": pc.unit_cost,
            "computed_at": pc.computed_at.isoformat() if pc.computed_at else None,
        })

    return {
        "status": "success",
        "cell": cell,
        "total": total,
        "limit": limit,
        "offset": offset,
        "policy": {
            "review_strategy": policy.review_strategy if policy else "CONTINUOUS",
            "target_service_level": policy.target_service_level if policy else 0.95,
            "safety_stock_policy": policy.safety_stock_policy if policy else "STANDARD_KINGS",
            "reorder_automation": policy.reorder_automation if policy else "AUTOMATED",
            "description": policy.description if policy else "",
        } if policy else None,
        "skus": items,
    }


def update_cell_policy(
    db: Session,
    cell: str,
    review_strategy: Optional[str] = None,
    target_service_level: Optional[float] = None,
    safety_stock_policy: Optional[str] = None,
    reorder_automation: Optional[str] = None,
    review_frequency_days: Optional[int] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Updates the configurable policy settings for a specific ABC-XYZ cell.
    """
    cell = cell.upper()
    pol = db.query(AbcXyzPolicy).filter(AbcXyzPolicy.cell == cell).first()
    if not pol:
        pol = AbcXyzPolicy(
            cell=cell,
            abc_class=cell[0],
            xyz_class=cell[1]
        )
        db.add(pol)

    if review_strategy is not None:
        pol.review_strategy = review_strategy
    if target_service_level is not None:
        pol.target_service_level = max(0.0, min(1.0, float(target_service_level)))
    if safety_stock_policy is not None:
        pol.safety_stock_policy = safety_stock_policy
    if reorder_automation is not None:
        pol.reorder_automation = reorder_automation
    if review_frequency_days is not None:
        pol.review_frequency_days = max(1, int(review_frequency_days))
    if description is not None:
        pol.description = description

    db.commit()
    db.refresh(pol)

    return {
        "status": "success",
        "cell": pol.cell,
        "review_strategy": pol.review_strategy,
        "target_service_level": pol.target_service_level,
        "safety_stock_policy": pol.safety_stock_policy,
        "reorder_automation": pol.reorder_automation,
        "review_frequency_days": pol.review_frequency_days,
        "description": pol.description,
    }
