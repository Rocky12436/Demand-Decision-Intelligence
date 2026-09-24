"""
Probabilistic Quantile Forecaster with Intermittent Bootstrapping and Pinball Loss Evaluation
Project: Demand-Decision-Intelligence
Phase 5 - Prompt 5.2
"""

import math
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from scipy import stats


DEFAULT_QUANTILES = [0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
QUANTILE_KEYS = ["q05", "q25", "q50", "q75", "q90", "q95", "q99"]


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, tau: float) -> float:
    """
    Computes asymmetric quantile loss (pinball loss) for a given quantile tau.
    L_tau(y, q) = max(tau * (y - q), (tau - 1) * (y - q))
    """
    diff = y_true - y_pred
    loss = np.maximum(tau * diff, (tau - 1.0) * diff)
    return float(np.mean(loss))


def compute_calibration_coverage(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Computes percentage of actual observations <= predicted quantile.
    """
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(y_true <= y_pred) * 100.0)


def bootstrap_intermittent_lead_time_demand(
    quantities: List[float],
    lead_time_days: int = 7,
    n_simulations: int = 3000,
    seed: Optional[int] = 42
) -> np.ndarray:
    """
    Non-parametric bootstrapping for intermittent demand (Croston/SBA).
    Avoids false Gaussian/normality assumptions for sparse or zero-inflated demand.
    Simulates cumulative lead-time demand by sampling non-zero demand sizes and
    inter-arrival periods empirically.
    """
    rng = np.random.default_rng(seed)
    arr = np.array(quantities, dtype=float)
    non_zero_sizes = arr[arr > 0]

    if len(non_zero_sizes) == 0:
        return np.zeros(n_simulations)

    # Calculate empirical inter-arrival intervals
    non_zero_indices = np.where(arr > 0)[0]
    if len(non_zero_indices) > 1:
        intervals = np.diff(non_zero_indices)
    else:
        intervals = np.array([len(arr)])

    # Probability of demand occurrence on any given day: p = 1 / mean_interval
    mean_interval = max(1.0, float(np.mean(intervals)))
    p_arrival = min(1.0, 1.0 / mean_interval)

    # Simulate demand over lead_time_days across n_simulations
    # Binomial arrival: number of demand occurrences in L days ~ Binomial(L, p_arrival)
    arrivals_count = rng.binomial(n=max(1, lead_time_days), p=p_arrival, size=n_simulations)

    # For each simulation, sum random sizes drawn from observed positive demands
    simulated_totals = np.zeros(n_simulations)
    for i, count in enumerate(arrivals_count):
        if count > 0:
            sizes = rng.choice(non_zero_sizes, size=count, replace=True)
            simulated_totals[i] = np.sum(sizes)

    return simulated_totals


def compute_quantiles_for_series(
    quantities: List[float],
    predicted_mean: float,
    std_dev: float,
    is_intermittent: bool = False,
    quantiles: List[float] = DEFAULT_QUANTILES,
    horizon_days: int = 14,
    seed: Optional[int] = 42
) -> Dict[str, float]:
    """
    Computes daily quantile values for a forecast.
    If intermittent: uses empirical bootstrap of non-zero sizes and inter-arrival rate.
    If regular: uses empirical residuals if sample size >= 15, otherwise calibrated Gaussian quantiles.
    """
    arr = np.array(quantities, dtype=float)
    results = {}

    if is_intermittent:
        # Intermittent daily simulation
        rng = np.random.default_rng(seed)
        non_zero = arr[arr > 0]
        if len(non_zero) == 0:
            for q in quantiles:
                key = f"q{int(round(q * 100)):02d}"
                results[key] = 0.0
            return results

        zero_prob = float(np.mean(arr == 0))
        n_boot = 5000
        # Draw Bernoulli for non-zero vs zero
        has_demand = rng.random(n_boot) > zero_prob
        sim_daily = np.zeros(n_boot)
        if np.any(has_demand):
            sim_daily[has_demand] = rng.choice(non_zero, size=int(np.sum(has_demand)), replace=True)

        for q in quantiles:
            val = float(np.percentile(sim_daily, q * 100))
            key = f"q{int(round(q * 100)):02d}"
            results[key] = round(max(0.0, val), 2)

    else:
        # Continuous / regular demand
        if len(arr) >= 20:
            # Empirical residuals
            residuals = arr - predicted_mean
            for q in quantiles:
                q_resid = float(np.percentile(residuals, q * 100))
                val = max(0.0, predicted_mean + q_resid)
                key = f"q{int(round(q * 100)):02d}"
                results[key] = round(val, 2)
        else:
            # Parametric Gaussian
            sigma = max(0.1, std_dev)
            for q in quantiles:
                z = stats.norm.ppf(q)
                val = max(0.0, predicted_mean + z * sigma)
                key = f"q{int(round(q * 100)):02d}"
                results[key] = round(val, 2)

    return results


def evaluate_quantiles_accuracy(
    quantities: List[float],
    quantiles_dict: Dict[str, float]
) -> Dict[str, Any]:
    """
    Evaluates pinball loss across quantiles and 90% calibration coverage against historical data.
    """
    if not quantities:
        return {"mean_pinball_loss": 0.0, "pinball_losses": {}, "calibration_coverage_90": 0.0}

    arr = np.array(quantities, dtype=float)
    losses = {}
    
    for key, val in quantiles_dict.items():
        # Parse tau from key, e.g. "q90" -> 0.90
        try:
            tau = float(key.replace("q", "")) / 100.0
            pred_arr = np.full_like(arr, val)
            losses[key] = round(pinball_loss(arr, pred_arr, tau), 4)
        except Exception:
            continue

    q90_val = quantiles_dict.get("q90", quantiles_dict.get("q95", 0.0))
    coverage_90 = round(compute_calibration_coverage(arr, np.full_like(arr, q90_val)), 2)
    mean_loss = round(float(np.mean(list(losses.values()))), 4) if losses else 0.0

    return {
        "mean_pinball_loss": mean_loss,
        "pinball_losses": losses,
        "calibration_coverage_90": coverage_90,
        "nominal_coverage_90": 90.0,
        "calibration_error": round(abs(coverage_90 - 90.0), 2),
    }


def compute_quantile_safety_stock(
    quantities: List[float],
    service_level: float = 0.95,
    lead_time_days: int = 7,
    sigma_lead_time_days: float = 0.0,
    is_intermittent: bool = False
) -> Dict[str, Any]:
    """
    Computes direct quantile safety stock:
      SS_quantile = Quantile(service_level of cumulative lead-time demand) - (lead_time * mean_demand)
    
    Also computes:
      - King's formula: Z * sqrt( L * sigma_d^2 + d_bar^2 * sigma_L^2 )
      - Classical formula: ceil( Z * sigma_d * sqrt(L) )
      
    Returns comparison delta demonstrating how quantile safety stock prevents over-buffering
    or under-buffering for skewed/intermittent distributions.
    """
    arr = np.array(quantities, dtype=float)
    if len(arr) == 0:
        return {
            "ss_quantile": 0.0,
            "ss_kings": 0.0,
            "ss_classical": 0.0,
            "delta_vs_kings": 0.0,
            "delta_vs_classical": 0.0,
            "service_level": service_level,
            "lead_time_days": lead_time_days,
        }

    d_bar = float(np.mean(arr))
    sigma_d = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    z = float(stats.norm.ppf(service_level)) if 0.0 < service_level < 1.0 else 1.645

    # 1. Classical formula: ceil(Z * sigma_d * sqrt(L))
    classical_val = math.ceil(z * sigma_d * math.sqrt(lead_time_days))

    # 2. King's formula: Z * sqrt( L * sigma_d^2 + d_bar^2 * sigma_L^2 )
    kings_inner = lead_time_days * (sigma_d ** 2) + (d_bar ** 2) * (sigma_lead_time_days ** 2)
    kings_val = round(z * math.sqrt(max(0.0, kings_inner)), 2)

    # 3. Direct Quantile Safety Stock
    if is_intermittent or len(arr[arr == 0]) / len(arr) > 0.3:
        # Bootstrapped lead-time demand distribution
        simulated_lead_time_demand = bootstrap_intermittent_lead_time_demand(
            quantities=quantities,
            lead_time_days=lead_time_days,
            n_simulations=4000
        )
        lead_time_demand_quantile = float(np.percentile(simulated_lead_time_demand, service_level * 100))
        expected_lead_time_demand = lead_time_days * d_bar
        quantile_ss = max(0.0, lead_time_demand_quantile - expected_lead_time_demand)
    else:
        # Continuous empirical lead-time accumulation or convolution
        # Random block sampling of L consecutive days or L independent days
        rng = np.random.default_rng(42)
        n_sim = 4000
        # Draw L days per simulation
        sim_draws = rng.choice(arr, size=(n_sim, max(1, lead_time_days)), replace=True)
        lead_time_sums = np.sum(sim_draws, axis=1)
        lead_time_demand_quantile = float(np.percentile(lead_time_sums, service_level * 100))
        expected_lead_time_demand = lead_time_days * d_bar
        quantile_ss = max(0.0, lead_time_demand_quantile - expected_lead_time_demand)

    quantile_ss_val = round(quantile_ss, 2)

    return {
        "ss_quantile": quantile_ss_val,
        "ss_kings": kings_val,
        "ss_classical": classical_val,
        "delta_vs_kings": round(quantile_ss_val - kings_val, 2),
        "delta_vs_classical": round(quantile_ss_val - classical_val, 2),
        "service_level": service_level,
        "lead_time_days": lead_time_days,
        "d_bar": round(d_bar, 2),
        "sigma_d": round(sigma_d, 2),
        "sigma_L": round(sigma_lead_time_days, 2),
    }
