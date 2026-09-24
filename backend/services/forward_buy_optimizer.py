"""
backend/services/forward_buy_optimizer.py
-----------------------------------------
Implementation of Prompt 4.3: Quantified Bulk Purchase Decision.
Calculates optimal forward-buy cover days and order quantity:
- Balances price surge savings against capital holding cost
- Enforces shelf-life safety margin (0.8 * shelf_life_days)
- Enforces warehouse storage capacity and available capital limits
- Identifies binding constraint (shelf_life, capital, capacity, economics)
- Performs 25th / 50th / 75th percentile sensitivity analysis
- Produces analytical curve data for frontend visualization
"""

import math
from typing import Dict, Any, List, Optional


def compute_optimal_forward_buy(
    d_bar: float,
    sigma_d: float,
    current_price: float,
    expected_future_price: Optional[float] = None,
    delta_pct: Optional[float] = None,
    holding_cost_rate: float = 0.25,
    shelf_life_days: int = 180,
    storage_capacity_units: float = 1000.0,
    available_capital: float = 500000.0,
    order_cost: float = 500.0,
    service_level: float = 0.95,
    safety_margin: float = 0.8,
) -> Dict[str, Any]:
    """
    Computes optimal days of forward cover and order quantity.
    """
    if d_bar <= 0:
        return {
            "recommended_quantity": 0,
            "days_of_cover": 0,
            "total_cost": 0.0,
            "savings_vs_no_action": 0.0,
            "capital_required": 0.0,
            "breakeven_days": 0,
            "binding_constraint": "zero_demand",
            "confidence": "HIGH",
            "sensitivity": {},
            "curve_points": []
        }

    # Resolve delta_pct and future price
    if expected_future_price is not None and expected_future_price > 0:
        delta_p = expected_future_price - current_price
        pct = (delta_p / current_price) if current_price > 0 else 0.0
    elif delta_pct is not None:
        pct = float(delta_pct)
        delta_p = current_price * pct
        expected_future_price = current_price + delta_p
    else:
        pct = 0.10 # default 10% rise
        delta_p = current_price * pct
        expected_future_price = current_price + delta_p

    if delta_p <= 0:
        return {
            "recommended_quantity": 0,
            "days_of_cover": 0,
            "total_cost": 0.0,
            "savings_vs_no_action": 0.0,
            "capital_required": 0.0,
            "breakeven_days": 0,
            "binding_constraint": "negative_or_zero_price_delta",
            "confidence": "HIGH",
            "sensitivity": {},
            "curve_points": []
        }

    # 1. Calculate Constraint Limits on Days of Cover
    # Constraint A: Shelf life safety limit
    d_max_shelf = float(shelf_life_days) * safety_margin

    # Constraint B: Warehouse storage capacity
    d_max_cap = storage_capacity_units / d_bar if d_bar > 0 else 0.0

    # Constraint C: Available working capital
    daily_spend = d_bar * current_price
    d_max_capital = available_capital / daily_spend if daily_spend > 0 else 0.0

    # Constraint D: Economic optimum (where marginal savings == marginal holding cost)
    # Holding cost = Q * P * h * (D / 730) = (d_bar * P * h / 730) * D^2
    # d/dD (Holding cost) = (d_bar * P * h / 365) * D
    # Savings = Q * delta_p = D * d_bar * delta_p
    # d/dD (Savings) = d_bar * delta_p
    # Setting equal: d_bar * delta_p = (d_bar * P * h / 365) * D => D* = (delta_p / P) * (365 / h)
    d_opt_econ = (pct / holding_cost_rate) * 365.0 if holding_cost_rate > 0 else 180.0

    # Maximum feasible days of cover
    d_optimal = max(0.0, min(d_opt_econ, d_max_shelf, d_max_cap, d_max_capital, 180.0))

    # Identify binding constraint
    if math.isclose(d_optimal, d_max_shelf, abs_tol=0.1):
        binding = "shelf_life"
    elif math.isclose(d_optimal, d_max_cap, abs_tol=0.1):
        binding = "storage_capacity"
    elif math.isclose(d_optimal, d_max_capital, abs_tol=0.1):
        binding = "available_capital"
    else:
        binding = "economics"

    # Quantities and financials at optimum
    q_opt = round(d_optimal * d_bar)
    capital_req = q_opt * current_price
    savings = q_opt * delta_p
    avg_days_held = d_optimal / 2.0
    holding_cost = q_opt * current_price * holding_cost_rate * (avg_days_held / 365.0)
    net_benefit = savings - holding_cost

    # Breakeven days (when holding cost equals total savings)
    breakeven_days = round((pct / holding_cost_rate) * 365.0 * 2.0, 1)

    # 2. Generate Sensitivity Analysis (25th, 50th, 75th percentiles of price move)
    sensitivity = {}
    for label, factor in [("p25_conservative", 0.5), ("p50_expected", 1.0), ("p75_aggressive", 1.5)]:
        scen_pct = pct * factor
        scen_d_econ = (scen_pct / holding_cost_rate) * 365.0
        scen_d = max(0.0, min(scen_d_econ, d_max_shelf, d_max_cap, d_max_capital, 180.0))
        scen_q = round(scen_d * d_bar)
        scen_savings = scen_q * (current_price * scen_pct)
        scen_holding = scen_q * current_price * holding_cost_rate * ((scen_d / 2.0) / 365.0)
        sensitivity[label] = {
            "price_surge_pct": round(scen_pct * 100, 1),
            "optimal_days_cover": round(scen_d, 1),
            "recommended_quantity": scen_q,
            "net_benefit_rs": round(scen_savings - scen_holding, 2),
            "capital_required_rs": round(scen_q * current_price, 2)
        }

    # 3. Generate Curve Points for Charting (0 to max cover)
    curve_points = []
    max_eval_d = min(180, int(d_max_shelf + 10))
    step = max(2, max_eval_d // 15)

    for d in range(0, max_eval_d + step, step):
        q = d * d_bar
        s = q * delta_p
        h = q * current_price * holding_cost_rate * ((d / 2.0) / 365.0)
        nb = s - h
        curve_points.append({
            "days_of_cover": d,
            "quantity": round(q, 1),
            "savings": round(s, 2),
            "holding_cost": round(h, 2),
            "net_benefit": round(nb, 2),
            "is_optimum": bool(abs(d - d_optimal) < step / 2.0)
        })

    return {
        "recommended_quantity": q_opt,
        "days_of_cover": round(d_optimal, 1),
        "total_cost": round(capital_req, 2),
        "savings_vs_no_action": round(savings, 2),
        "holding_cost": round(holding_cost, 2),
        "net_benefit": round(net_benefit, 2),
        "capital_required": round(capital_req, 2),
        "breakeven_days": breakeven_days,
        "binding_constraint": binding,
        "confidence": "HIGH" if d_bar > 10 else "MEDIUM",
        "limits": {
            "max_shelf_life_days": round(d_max_shelf, 1),
            "max_capacity_days": round(d_max_cap, 1),
            "max_capital_days": round(d_max_capital, 1),
            "economic_optimal_days": round(d_opt_econ, 1),
        },
        "sensitivity": sensitivity,
        "curve_points": curve_points
    }
