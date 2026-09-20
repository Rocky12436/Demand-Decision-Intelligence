"""
Pricing API Router (Stage 7)
Project: Demand-Decision-Intelligence System
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from analytics.price_elasticity_engine import PriceElasticityEngine, REPORT_JSON

router = APIRouter()


def _get_or_generate_report() -> Dict[str, Any]:
    """Helper to load precomputed elasticity report or generate it if missing."""
    if REPORT_JSON.exists():
        try:
            with open(REPORT_JSON, "r") as f:
                return json.load(f)
        except Exception:
            pass

    # Run engine dynamically if report missing or corrupt
    engine = PriceElasticityEngine()
    return engine.run_analysis()


@router.get("/elasticity")
def get_elasticity_insights(
    limit: int = Query(50, ge=1, le=1000, description="Number of SKUs to return"),
    classification: Optional[str] = Query(None, description="Filter by classification: Elastic, Inelastic, Anomalous"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    """
    Returns Price Elasticity of Demand (PED) insights for SKUs.
    Includes PED coefficient, category classification, avg daily volume/price/revenue, and projected impact.
    """
    report = _get_or_generate_report()
    skus = report.get("skus", [])

    if classification:
        skus = [s for s in skus if s.get("classification", "").lower() == classification.lower()]

    if category:
        skus = [s for s in skus if category.lower() in s.get("category", "").lower()]

    limited_skus = skus[:limit]

    return {
        "status": "success",
        "metadata": report.get("metadata", {}),
        "total_returned": len(limited_skus),
        "skus": limited_skus
    }


@router.get("/recommendations")
def get_pricing_recommendations(
    category: Optional[str] = Query(None, description="Filter by product category"),
    limit: int = Query(50, ge=1, le=500, description="Limit output count")
):
    """
    Returns optimal price and discount recommendations per SKU.
    """
    report = _get_or_generate_report()
    skus = report.get("skus", [])

    if category:
        skus = [s for s in skus if category.lower() in s.get("category", "").lower()]

    recommendations = []
    for s in skus[:limit]:
        recommendations.append({
            "product_id": s["product_id"],
            "product_name": s["product_name"],
            "category": s["category"],
            "brand": s["brand"],
            "current_price": s["avg_unit_price"],
            "optimal_price": s["optimal_price"],
            "recommended_discount_pct": s["recommended_discount_pct"],
            "classification": s["classification"],
            "price_elasticity": s["price_elasticity"],
            "projected_vol_change_pct": s["projected_vol_change_pct"],
            "projected_revenue_impact_pct": s["projected_revenue_impact_pct"],
            "action_recommendation": s["action_recommendation"]
        })

    return {
        "status": "success",
        "summary": report.get("metadata", {}),
        "total_recommendations": len(recommendations),
        "recommendations": recommendations
    }


@router.post("/recalculate")
def recalculate_elasticity():
    """
    Triggers recalculation of the Price Elasticity Engine.
    """
    try:
        engine = PriceElasticityEngine()
        report = engine.run_analysis()
        return {
            "status": "success",
            "message": "Price Elasticity Engine recalculated successfully.",
            "metadata": report.get("metadata", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to recalculate elasticity: {str(e)}")
