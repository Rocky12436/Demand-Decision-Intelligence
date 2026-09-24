"""
backend/services/budget_allocator.py
------------------------------------
Capital Allocation Engine: "What Should I Buy With The Money I Have"

Solves the constrained procurement knapsack problem:
Given a limited working capital budget B, determines the optimal set of SKUs
to replenish to maximize expected stockout cost avoided across a given horizon.

Algorithmic Design:
1. Demand Uncertainty & Stockout Distribution:
   - For horizon H days:
     mu_H = H * d_bar
     sigma_H = sqrt(H) * sigma_d
   - P(stockout within horizon) = P(D_H > S) = 1 - Phi( (S - mu_H) / sigma_H )
   - Expected lost units using First Order Normal Loss Function:
     E[lost_units] = sigma_H * [ phi(z) - z * (1 - Phi(z)) ] where z = (S - mu_H) / sigma_H
   - Expected stockout cost avoided:
     Benefit = P(stockout within horizon) * E[lost_units] * margin_per_unit

2. Discrete Replenishment Constraints:
   - raw_qty = max(0, TSL - on_hand)
   - order_qty = round_to_moq_and_pack_size(raw_qty, moq, pack_size)
   - order_cost = order_qty * unit_cost

3. Optimization (Knapsack):
   - Continuous/Fractional relaxation: rank items by Benefit / Cost (greedy-fill).
   - 0/1 Knapsack Refinement: Because MOQ and pack size induce 0/1 lumpiness,
     when candidate SKU count <= 500, a dynamic programming (DP) refinement
     over a discretized capacity grid is run to find superior discrete packing.
   - For candidate SKU count > 500, the system falls back to the greedy fractional
     knapsack relaxation with integer floor and greedy budget-residual top-up.

4. Output Analytics:
   - Selected SKUs with order quantities, costs, and risk mitigated.
   - Top 5 unselected SKUs (explicitly exposing the risk the business is accepting).
   - Diminishing returns curve: cumulative risk reduction vs spend showing the curve
     flattening at the economic optimal budget.
"""

import math
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.inventory import InventoryRecommendation, InventoryState
from backend.models.procurement import SupplierProduct
from backend.models.demand import DailyProductDemand
from backend.models.product import Product
from backend.services.procurement_service import round_to_moq_and_pack_size
from backend.services.dataset_service import resolve_dataset


def normal_pdf(z: float) -> float:
    """Standard normal probability density function phi(z)."""
    return math.exp(-0.5 * (z ** 2)) / math.sqrt(2.0 * math.pi)


def normal_cdf(z: float) -> float:
    """Standard normal cumulative distribution function Phi(z)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_stockout_probability_and_lost_units(
    current_stock: float,
    mean_daily_demand: float,
    std_daily_demand: float,
    horizon_days: int = 14,
) -> Tuple[float, float]:
    """
    Computes P(stockout within horizon) and E[lost_units] under a Normal
    distribution over the demand horizon.

    Returns:
        (p_stockout, expected_lost_units)
    """
    h = max(1, int(horizon_days))
    d_bar = max(0.0, float(mean_daily_demand))
    sigma_d = max(0.0, float(std_daily_demand))
    s = max(0.0, float(current_stock))

    # If std_daily is zero or near zero, use a minimal CV of 15% to avoid degenerate zero variance
    if sigma_d < 1e-4:
        sigma_d = max(0.5, 0.15 * d_bar)

    mu_h = h * d_bar
    sigma_h = math.sqrt(h) * sigma_d

    if sigma_h <= 1e-4:
        # Deterministic boundary
        if s < mu_h:
            return 1.0, round(mu_h - s, 2)
        return 0.0, 0.0

    z = (s - mu_h) / sigma_h

    # P(stockout within horizon) = 1 - Phi(z) = 0.5 * erfc(z / sqrt(2))
    p_stockout = max(0.0, min(1.0, 1.0 - normal_cdf(z)))

    # First Order Normal Loss function:
    # E[max(0, D_H - S)] = sigma_H * [ phi(z) - z * (1 - Phi(z)) ]
    phi_z = normal_pdf(z)
    loss_integral = sigma_h * (phi_z - (z * p_stockout))
    expected_lost_units = max(0.0, round(loss_integral, 2))

    return round(p_stockout, 4), expected_lost_units


def solve_01_knapsack_dp(
    items: List[Dict[str, Any]],
    budget: float,
    grid_size: int = 1000
) -> List[int]:
    """
    0/1 Knapsack Dynamic Programming refinement for discrete MOQ/pack-size orders.
    Discretizes budget into grid_size capacity steps to keep time and space bounded O(N * grid_size).

    Returns:
        List of item indices selected by DP.
    """
    if not items or budget <= 0:
        return []

    n = len(items)
    b_float = float(budget)
    scale = b_float / float(grid_size)

    # Weights in discrete grid units
    weights = [max(1, int(math.ceil(it["cost"] / scale))) for it in items]
    values = [it["expected_stockout_cost_avoided"] for it in items]

    # dp[w] stores max value achievable with discrete weight w
    dp = [0.0] * (grid_size + 1)
    # keep track of chosen items using a bitmask or set
    chosen: List[List[int]] = [[] for _ in range(grid_size + 1)]

    for i in range(n):
        w_i = weights[i]
        v_i = values[i]
        if w_i > grid_size:
            continue
        for w in range(grid_size, w_i - 1, -1):
            if dp[w - w_i] + v_i > dp[w]:
                dp[w] = dp[w - w_i] + v_i
                chosen[w] = chosen[w - w_i] + [i]

    # Find best w <= grid_size whose exact cost does not exceed budget
    best_indices = []
    best_exact_val = 0.0

    for w in range(grid_size, -1, -1):
        candidate_indices = chosen[w]
        exact_cost = sum(items[idx]["cost"] for idx in candidate_indices)
        if exact_cost <= b_float:
            exact_val = sum(items[idx]["expected_stockout_cost_avoided"] for idx in candidate_indices)
            if exact_val > best_exact_val:
                best_exact_val = exact_val
                best_indices = candidate_indices

    return best_indices


def generate_diminishing_returns_curve(
    ranked_candidates: List[Dict[str, Any]],
    budget: float,
    num_points: int = 30
) -> List[Dict[str, Any]]:
    """
    Generates cumulative risk reduction vs spend curve showing the flattening
    diminishing returns knee.
    """
    if not ranked_candidates:
        step = max(budget, 10000.0) / float(num_points)
        return [
            {"spend": round(p * step, 2), "cumulative_risk_avoided": 0.0, "sku_count": 0}
            for p in range(num_points + 1)
        ]

    total_candidate_spend = sum(it["cost"] for it in ranked_candidates)
    max_spend_axis = max(budget * 1.5, min(total_candidate_spend, budget * 3.0))
    if max_spend_axis <= 0:
        max_spend_axis = 10000.0

    step = max_spend_axis / float(num_points)
    curve = []

    # Precompute prefix sums of greedy ranking
    prefix_spend = [0.0]
    prefix_benefit = [0.0]
    for it in ranked_candidates:
        prefix_spend.append(prefix_spend[-1] + it["cost"])
        prefix_benefit.append(prefix_benefit[-1] + it["expected_stockout_cost_avoided"])

    for p in range(num_points + 1):
        target_spend = p * step
        # find how many items fit target_spend
        idx = 0
        while idx < len(ranked_candidates) and prefix_spend[idx + 1] <= target_spend:
            idx += 1

        cum_benefit = prefix_benefit[idx]
        # Partial fractional addition for smooth curve visualization
        if idx < len(ranked_candidates) and target_spend > prefix_spend[idx]:
            rem_spend = target_spend - prefix_spend[idx]
            next_item = ranked_candidates[idx]
            fraction = min(1.0, rem_spend / max(1.0, next_item["cost"]))
            cum_benefit += fraction * next_item["expected_stockout_cost_avoided"]

        curve.append({
            "spend": round(target_spend, 2),
            "cumulative_risk_avoided": round(cum_benefit, 2),
            "sku_count": idx,
        })

    return curve


def allocate_budget(
    db: Session,
    dataset_id: Optional[int] = None,
    budget: float = 100000.0,
    horizon_days: int = 14,
    location_id: Optional[str] = None,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes the 'What Should I Buy With The Money I Have' inventory budget allocation.

    Steps:
    1. Gathers all SKUs below ROP or needing replenishment in the dataset.
    2. Computes P(stockout within horizon) from forecast distribution.
    3. Computes E[lost_units] using normal distribution first-order loss integral.
    4. Computes margin per unit (selling_price - unit_cost).
    5. Computes Expected Stockout Cost Avoided = P(stockout) * E[lost_units] * margin.
    6. Respects preferred supplier MOQ and pack size multiples.
    7. Evaluates Benefit / Cost ratio and runs 0/1 Knapsack DP refinement (when N <= 500).
    8. Returns selected SKUs, spend summary, top 5 risk-accepted SKUs, and the diminishing returns curve.
    """
    target_dataset = resolve_dataset(db, None, dataset_id)
    budget = max(0.0, float(budget))
    horizon_days = max(1, int(horizon_days))

    # 1. Fetch recommendations / candidate SKUs
    rec_query = db.query(InventoryRecommendation).filter(
        InventoryRecommendation.dataset_id == target_dataset.id
    )
    if location_id and location_id != "ALL":
        rec_query = rec_query.filter(InventoryRecommendation.city_name == location_id)

    recommendations = rec_query.all()

    candidates: List[Dict[str, Any]] = []

    # Map supplier products for MOQ, pack size, and unit cost
    supplier_prods = {
        sp.product_id: sp
        for sp in db.query(SupplierProduct).filter(SupplierProduct.is_preferred == True).all()
    }
    # Also fetch all supplier products to fallback if no is_preferred is explicitly true
    all_supplier_prods = {
        sp.product_id: sp
        for sp in db.query(SupplierProduct).all()
    }

    # Fetch products for names
    products = {p.product_id: p for p in db.query(Product).all()}

    # Fallback to daily demand if InventoryRecommendation table has few or zero records
    if not recommendations:
        # Build candidate SKUs from DailyProductDemand
        demand_query = db.query(
            DailyProductDemand.product_id,
            DailyProductDemand.city_name,
            func.avg(DailyProductDemand.total_quantity).label("mean_demand"),
            func.stddev(DailyProductDemand.total_quantity).label("std_demand"),
            func.avg(DailyProductDemand.avg_unit_price).label("avg_price")
        ).filter(
            DailyProductDemand.dataset_id == target_dataset.id
        )
        if location_id and location_id != "ALL":
            demand_query = demand_query.filter(DailyProductDemand.city_name == location_id)

        agg_demands = demand_query.group_by(DailyProductDemand.product_id, DailyProductDemand.city_name).all()

        for row in agg_demands:
            prod_id = str(row.product_id)
            city = str(row.city_name)
            mean_d = float(row.mean_demand or 5.0)
            std_d = float(row.std_demand or (0.35 * mean_d))
            avg_price = float(row.avg_price or 50.0)

            # Look up supplier info
            sp = supplier_prods.get(prod_id) or all_supplier_prods.get(prod_id)
            unit_cost = float(sp.unit_cost) if sp and sp.unit_cost > 0 else round(avg_price * 0.75, 2)
            moq = int(sp.moq) if sp and sp.moq else 1
            pack_size = int(sp.order_multiple) if sp and sp.order_multiple else 1

            # Simulated on-hand stock and lead time
            lead_time = int(sp.promised_lead_time_days) if sp and sp.promised_lead_time_days else 3
            rop = round(mean_d * lead_time + (1.645 * std_d * math.sqrt(lead_time)), 2)
            tsl = round(rop + (mean_d * horizon_days), 2)
            current_stock = round(rop * 0.4, 2)  # Below ROP candidate

            margin = max(1.0, round(avg_price - unit_cost, 2))
            p_stockout, lost_units = compute_stockout_probability_and_lost_units(
                current_stock=current_stock,
                mean_daily_demand=mean_d,
                std_daily_demand=std_d,
                horizon_days=horizon_days,
            )

            # Raw needed quantity to bring to TSL
            raw_qty = max(0.0, tsl - current_stock)
            order_qty = round_to_moq_and_pack_size(raw_qty, moq, pack_size)
            cost = round(order_qty * unit_cost, 2)

            # Benefit = P(stockout within horizon) * expected_lost_units * margin_per_unit
            expected_stockout_cost_avoided = round(p_stockout * lost_units * margin, 2)
            ratio = round(expected_stockout_cost_avoided / cost, 4) if cost > 0 else 0.0

            prod_obj = products.get(prod_id)
            prod_name = prod_obj.product_name if prod_obj else f"Product #{prod_id}"

            candidates.append({
                "product_id": prod_id,
                "product_name": prod_name,
                "city_name": city,
                "current_stock": current_stock,
                "rop": rop,
                "tsl": tsl,
                "mean_daily_demand": round(mean_d, 2),
                "std_daily_demand": round(std_d, 2),
                "horizon_days": horizon_days,
                "p_stockout": p_stockout,
                "expected_lost_units": lost_units,
                "selling_price": avg_price,
                "unit_cost": unit_cost,
                "margin_per_unit": margin,
                "moq": moq,
                "pack_size": pack_size,
                "raw_quantity": round(raw_qty, 2),
                "order_quantity": order_qty,
                "cost": cost,
                "expected_stockout_cost_avoided": expected_stockout_cost_avoided,
                "benefit_cost_ratio": ratio,
            })
    else:
        for rec in recommendations:
            prod_id = str(rec.product_id)
            city = str(rec.city_name)
            current_stock = float(rec.current_stock or 0.0)
            rop = float(rec.reorder_point or 0.0)

            # Only consider SKUs needing replenishment (current_stock < ROP or recommended_order_qty > 0)
            mean_d = float(rec.avg_daily_demand or 5.0)
            std_d = 0.35 * mean_d

            # If current_stock >= rop and rec.recommended_order_qty <= 0, skip
            if current_stock >= rop and (rec.recommended_order_qty or 0) <= 0:
                continue

            sp = supplier_prods.get(prod_id) or all_supplier_prods.get(prod_id)
            moq = int(sp.moq) if sp and sp.moq else 1
            pack_size = int(sp.order_multiple) if sp and sp.order_multiple else 1

            # Estimate price & cost
            selling_price = 50.0
            last_demand = db.query(DailyProductDemand).filter(
                DailyProductDemand.dataset_id == target_dataset.id,
                DailyProductDemand.product_id == prod_id
            ).order_by(DailyProductDemand.date_.desc()).first()
            if last_demand and last_demand.avg_unit_price:
                selling_price = float(last_demand.avg_unit_price)

            unit_cost = float(sp.unit_cost) if sp and sp.unit_cost > 0 else round(selling_price * 0.75, 2)
            margin = max(1.0, round(selling_price - unit_cost, 2))

            tsl = round(rop + (mean_d * horizon_days), 2)
            raw_qty = max(float(rec.recommended_order_qty or 0.0), tsl - current_stock)
            order_qty = round_to_moq_and_pack_size(raw_qty, moq, pack_size)
            cost = round(order_qty * unit_cost, 2)

            p_stockout, lost_units = compute_stockout_probability_and_lost_units(
                current_stock=current_stock,
                mean_daily_demand=mean_d,
                std_daily_demand=std_d,
                horizon_days=horizon_days,
            )

            expected_stockout_cost_avoided = round(p_stockout * lost_units * margin, 2)
            ratio = round(expected_stockout_cost_avoided / cost, 4) if cost > 0 else 0.0

            prod_obj = products.get(prod_id)
            prod_name = prod_obj.product_name if prod_obj else f"Product #{prod_id}"

            candidates.append({
                "product_id": prod_id,
                "product_name": prod_name,
                "city_name": city,
                "current_stock": current_stock,
                "rop": rop,
                "tsl": tsl,
                "mean_daily_demand": round(mean_d, 2),
                "std_daily_demand": round(std_d, 2),
                "horizon_days": horizon_days,
                "p_stockout": p_stockout,
                "expected_lost_units": lost_units,
                "selling_price": selling_price,
                "unit_cost": unit_cost,
                "margin_per_unit": margin,
                "moq": moq,
                "pack_size": pack_size,
                "raw_quantity": round(raw_qty, 2),
                "order_quantity": order_qty,
                "cost": cost,
                "expected_stockout_cost_avoided": expected_stockout_cost_avoided,
                "benefit_cost_ratio": ratio,
            })

    # Sort candidates by benefit-to-cost ratio descending (greedy fractional relaxation)
    candidates.sort(key=lambda x: x["benefit_cost_ratio"], reverse=True)

    n_candidates = len(candidates)

    # Solve Knapsack
    # 1. Greedy solution
    greedy_selected_indices: List[int] = []
    current_spend = 0.0
    for idx, c in enumerate(candidates):
        if current_spend + c["cost"] <= budget:
            greedy_selected_indices.append(idx)
            current_spend += c["cost"]

    selected_indices = greedy_selected_indices

    # 2. If candidate count <= 500, execute 0/1 Knapsack DP refinement
    dp_used = False
    if n_candidates <= 500 and budget > 0:
        dp_indices = solve_01_knapsack_dp(candidates, budget, grid_size=1000)
        dp_benefit = sum(candidates[i]["expected_stockout_cost_avoided"] for i in dp_indices)
        greedy_benefit = sum(candidates[i]["expected_stockout_cost_avoided"] for i in greedy_selected_indices)

        if dp_benefit > greedy_benefit:
            selected_indices = dp_indices
            dp_used = True

    selected_indices_set = set(selected_indices)
    selected_skus = [candidates[i] for i in selected_indices]
    unselected_candidates = [candidates[i] for i in range(n_candidates) if i not in selected_indices_set]

    # Sort unselected by expected_stockout_cost_avoided descending to surface highest risk accepted
    unselected_candidates.sort(key=lambda x: x["expected_stockout_cost_avoided"], reverse=True)
    top_5_unselected = unselected_candidates[:5]

    total_spend = round(sum(it["cost"] for it in selected_skus), 2)
    budget_remaining = round(max(0.0, budget - total_spend), 2)
    total_stockout_cost_avoided = round(sum(it["expected_stockout_cost_avoided"] for it in selected_skus), 2)
    total_candidate_risk = round(sum(it["expected_stockout_cost_avoided"] for it in candidates), 2)
    unfunded_risk = round(max(0.0, total_candidate_risk - total_stockout_cost_avoided), 2)

    # Generate diminishing returns curve
    curve = generate_diminishing_returns_curve(candidates, budget=budget, num_points=30)

    return {
        "status": "success",
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "budget": budget,
        "horizon_days": horizon_days,
        "location_id": location_id or "ALL",
        "summary": {
            "budget": budget,
            "total_spend": total_spend,
            "budget_remaining": budget_remaining,
            "total_stockout_cost_avoided": total_stockout_cost_avoided,
            "total_candidate_risk": total_candidate_risk,
            "unfunded_risk_accepted": unfunded_risk,
            "risk_mitigation_pct": round((total_stockout_cost_avoided / total_candidate_risk * 100.0), 1) if total_candidate_risk > 0 else 100.0,
            "roi_ratio": round(total_stockout_cost_avoided / total_spend, 2) if total_spend > 0 else 0.0,
            "candidate_skus_count": n_candidates,
            "selected_skus_count": len(selected_skus),
            "unfunded_skus_count": len(unselected_candidates),
            "optimization_method": "0/1 Knapsack DP Refinement" if dp_used else ("Greedy Fractional-Knapsack Relaxation" if n_candidates > 500 else "Greedy Ratio-Ranked Pack"),
        },
        "selected_skus": selected_skus,
        "unselected_top_skus": top_5_unselected,
        "curve": curve,
    }
