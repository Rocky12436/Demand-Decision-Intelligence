"""
Classifier-Aware Anomaly Detection Service for Intermittent & Continuous Demand
Project: Demand-Decision-Intelligence
"""

import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from backend.models.demand import DailyProductDemand
from backend.models.anomaly import AnomalyAlert
from backend.models.dataset import Dataset


def classify_sbc(quantities: np.ndarray) -> str:
    """
    Syntetos-Boylan-Croston (SBC) Demand Categorization:
    Computes:
    - ADI (Average Demand Interval): total periods / count of non-zero demand periods
    - CV^2 (Squared Coefficient of Variation of non-zero demand): (std / mean)^2

    Cutoffs:
        ADI = 1.32, CV^2 = 0.49
    Categories:
        ADI < 1.32 and CV^2 < 0.49  -> SMOOTH
        ADI >= 1.32 and CV^2 < 0.49 -> INTERMITTENT
        ADI < 1.32 and CV^2 >= 0.49 -> ERRATIC
        ADI >= 1.32 and CV^2 >= 0.49 -> LUMPY
    """
    if len(quantities) == 0:
        return "SMOOTH"

    non_zero = quantities[quantities > 0]
    if len(non_zero) == 0:
        return "INTERMITTENT"

    adi = len(quantities) / len(non_zero)
    mean_nz = float(np.mean(non_zero))
    std_nz = float(np.std(non_zero, ddof=1)) if len(non_zero) > 1 else 0.0
    cv2 = ((std_nz / mean_nz) ** 2) if mean_nz > 0 else 0.0

    if adi < 1.32 and cv2 < 0.49:
        return "SMOOTH"
    elif adi >= 1.32 and cv2 < 0.49:
        return "INTERMITTENT"
    elif adi < 1.32 and cv2 >= 0.49:
        return "ERRATIC"
    else:
        return "LUMPY"


def compute_modified_z_score(x: float, median_val: float, mad_val: float) -> float:
    """
    Computes robust Modified Z-Score using median and MAD:
        Modified Z = 0.6745 * (x - median) / MAD
    Floors MAD at max(MAD, 1.0, 0.1 * median) to strictly prevent division-by-zero or explosion.
    """
    safe_mad = max(float(mad_val), 1.0, 0.1 * max(0.0, float(median_val)))
    return 0.6745 * (float(x) - float(median_val)) / safe_mad


def fit_count_model_p99(non_zero_values: np.ndarray) -> float:
    """
    Fits Negative Binomial (or Poisson if variance <= 1.5 * mean) to non-zero demand sizes
    and returns the 99th percentile threshold.
    """
    if len(non_zero_values) == 0:
        return 0.0

    mean_v = float(np.mean(non_zero_values))
    var_v = float(np.var(non_zero_values, ddof=1)) if len(non_zero_values) > 1 else 0.0

    # If variance <= 1.5 * mean or underdispersed: Poisson
    if var_v <= 1.5 * mean_v or var_v <= mean_v:
        # Poisson distribution with lambda = mean_v
        p99 = stats.poisson.ppf(0.99, max(0.1, mean_v))
        return float(max(p99, mean_v))

    # Overdispersed: Negative Binomial using method of moments
    # mean = r*(1-p)/p, variance = r*(1-p)/p^2 -> p = mean / variance, r = mean^2 / (variance - mean)
    p = mean_v / var_v
    p = max(0.001, min(0.999, p))
    r = (mean_v ** 2) / max(0.001, var_v - mean_v)
    r = max(0.1, r)

    p99 = stats.nbinom.ppf(0.99, r, p)
    return float(max(p99, mean_v))


def detect_interarrival_silence(dates: List[date], quantities: np.ndarray) -> Optional[Dict[str, Any]]:
    """
    Tracks inter-arrival intervals (days between non-zero sales).
    Flags 'unexpected silence' (STOCKOUT_SUSPECTED) if the trailing zero streak
    exceeds the 99th percentile of historical inter-arrival gaps.
    """
    if len(quantities) < 30:
        return None

    non_zero_indices = [i for i, q in enumerate(quantities) if q > 0]
    if len(non_zero_indices) < 2:
        return None

    # Calculate historical gaps in days between non-zero events
    gaps = []
    for j in range(1, len(non_zero_indices)):
        gap = non_zero_indices[j] - non_zero_indices[j - 1]
        gaps.append(gap)

    if not gaps:
        return None

    gap_p99 = float(np.percentile(gaps, 99))
    gap_threshold = max(gap_p99, 7.0)  # At least 7 consecutive zero days

    # Trailing streak of zero days at the end of the series
    trailing_zeros = len(quantities) - 1 - non_zero_indices[-1]
    if trailing_zeros > gap_threshold:
        return {
            "anomaly_type": "STOCKOUT_SUSPECTED",
            "detection_method": "INTERARRIVAL_GAP_SILENCE",
            "confidence": "HIGH",
            "severity": "CRITICAL",
            "gap_days": trailing_zeros,
            "threshold_days": round(gap_threshold, 1),
            "last_active_date": dates[non_zero_indices[-1]].isoformat(),
            "description": (
                f"Unexpected silence: {trailing_zeros} consecutive days with zero demand "
                f"exceeds historical 99th percentile interval ({round(gap_threshold, 1)} days). "
                f"Stockout suspected."
            ),
        }
    return None


def detect_anomalies_for_series(
    product_id: str,
    city_name: str,
    dates: List[date],
    quantities: List[float],
    min_observations: int = 30
) -> Dict[str, Any]:
    """
    Classifier-aware anomaly detection pipeline:
    1. Suppresses anomalies if observations < min_observations, labeling INSUFFICIENT_HISTORY.
    2. Routes by SBC classification (SMOOTH, ERRATIC, INTERMITTENT, LUMPY).
    3. SMOOTH/ERRATIC: Modified Z-score with median & MAD floored to prevent division-by-zero.
    4. INTERMITTENT/LUMPY: Count model (Negative Binomial / Poisson) on non-zero sizes + unexpected silence detection.
    """
    n_obs = len(quantities)
    q_arr = np.array(quantities, dtype=float)

    if n_obs < min_observations:
        return {
            "product_id": str(product_id),
            "city_name": city_name,
            "sbc_class": "UNKNOWN",
            "status": "INSUFFICIENT_HISTORY",
            "confidence": "INSUFFICIENT_HISTORY",
            "observations_count": n_obs,
            "anomalies": [],
            "message": f"Insufficient history: SKU has {n_obs} observations (minimum {min_observations} required). Alerts suppressed.",
        }

    sbc_class = classify_sbc(q_arr)
    detected_anomalies = []

    if sbc_class in ("SMOOTH", "ERRATIC"):
        # Modified Z-score with median and MAD over 14-day rolling window
        rolling_window = 14
        for idx in range(rolling_window, n_obs):
            window = q_arr[idx - rolling_window:idx]
            current_x = q_arr[idx]
            current_date = dates[idx]

            med = float(np.median(window))
            mad = float(np.median(np.abs(window - med)))
            mod_z = compute_modified_z_score(current_x, med, mad)

            if mod_z > 2.5:
                detected_anomalies.append({
                    "date_": current_date.isoformat(),
                    "product_id": str(product_id),
                    "city_name": city_name,
                    "anomaly_type": "SPIKE",
                    "detection_method": "MODIFIED_Z_MAD",
                    "confidence": "HIGH",
                    "severity": "CRITICAL" if mod_z >= 4.0 else "MEDIUM",
                    "actual_value": float(current_x),
                    "expected_value": round(med, 2),
                    "score": round(min(1.0, abs(mod_z) / 5.0), 4),
                    "description": f"Demand surge: observed {current_x} exceeds rolling median {round(med, 2)} (Modified Z = {round(mod_z, 2)})",
                })
            elif mod_z < -2.5 and med > 5.0:
                detected_anomalies.append({
                    "date_": current_date.isoformat(),
                    "product_id": str(product_id),
                    "city_name": city_name,
                    "anomaly_type": "DROP",
                    "detection_method": "MODIFIED_Z_MAD",
                    "confidence": "HIGH",
                    "severity": "CRITICAL" if mod_z <= -4.0 else "MEDIUM",
                    "actual_value": float(current_x),
                    "expected_value": round(med, 2),
                    "score": round(min(1.0, abs(mod_z) / 5.0), 4),
                    "description": f"Demand drop: observed {current_x} fell significantly below rolling median {round(med, 2)} (Modified Z = {round(mod_z, 2)})",
                })

    else:
        # INTERMITTENT or LUMPY -> Count Model, NO Z-scores!
        non_zero = q_arr[q_arr > 0]
        p99_threshold = fit_count_model_p99(non_zero)

        # Flag spikes on non-zero days only if exceeding 99th percentile
        for idx in range(n_obs):
            current_x = q_arr[idx]
            current_date = dates[idx]
            if current_x > 0 and current_x > p99_threshold:
                detected_anomalies.append({
                    "date_": current_date.isoformat(),
                    "product_id": str(product_id),
                    "city_name": city_name,
                    "anomaly_type": "SPIKE",
                    "detection_method": "COUNT_MODEL_NEGBINOMIAL",
                    "confidence": "HIGH",
                    "severity": "CRITICAL" if current_x > (p99_threshold * 1.5) else "MEDIUM",
                    "actual_value": float(current_x),
                    "expected_value": round(float(np.mean(non_zero)), 2),
                    "score": round(min(1.0, current_x / (p99_threshold + 1.0)), 4),
                    "description": f"Intermittent demand spike: {current_x} exceeds 99th percentile fitted count threshold ({round(p99_threshold, 2)})",
                })

        # Check for unexpected silence (stockout suspected)
        silence_alert = detect_interarrival_silence(dates, q_arr)
        if silence_alert:
            detected_anomalies.append({
                "date_": dates[-1].isoformat(),
                "product_id": str(product_id),
                "city_name": city_name,
                "anomaly_type": silence_alert["anomaly_type"],
                "detection_method": silence_alert["detection_method"],
                "confidence": silence_alert["confidence"],
                "severity": silence_alert["severity"],
                "actual_value": 0.0,
                "expected_value": round(float(np.mean(non_zero)), 2),
                "score": 0.95,
                "description": silence_alert["description"],
            })

    # Check for dead stock (zero demand for the last 60+ consecutive days when history >= 90 days)
    if n_obs >= 90 and np.all(q_arr[-60:] == 0):
        detected_anomalies.append({
            "date_": dates[-1].isoformat(),
            "product_id": str(product_id),
            "city_name": city_name,
            "anomaly_type": "DEAD_STOCK",
            "detection_method": "ZERO_DEMAND_PERSISTENCE",
            "confidence": "HIGH",
            "severity": "CRITICAL",
            "actual_value": 0.0,
            "expected_value": 0.0,
            "score": 0.99,
            "description": "Dead stock detected: zero demand recorded over the last 60 consecutive days.",
        })

    return {
        "product_id": str(product_id),
        "city_name": city_name,
        "sbc_class": sbc_class,
        "status": "COMPLETED",
        "confidence": "HIGH",
        "observations_count": n_obs,
        "anomalies": detected_anomalies,
    }
