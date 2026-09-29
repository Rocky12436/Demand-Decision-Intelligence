"""
Forecasting Engine v2 – accurate, traceable, per-model independent runs.

Key fixes vs v1:
  B1  model_requested saved separately; ineligible model → status=SKIPPED
  B2  Idempotency on (dataset_id, product_id, horizon, model_requested, data_version_hash)
  B3  Seasonal-naive DOW extrapolation + √horizon interval widening (not flat mean)
  B4  Walkforward backtest residuals used for coverage; no in-sample leakage
  B5  No hardcoded mock metrics anywhere

Project: Demand-Decision-Intelligence
"""

import hashlib
import json
import math
import uuid
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.demand import DailyProductDemand
from backend.models.forecast import ForecastRun, ForecastItem, ForecastEvaluation, ForecastJob
from backend.models.product import Product
from backend.models.upload import UploadJob


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_OBSERVATIONS: Dict[str, int] = {
    "Prophet_Yearly": 365,
    "Prophet": 120,
    "Prophet_Weekly": 120,
    "Prophet_MovingAvg_Ensemble": 120,
    "Ridge_LagFeatures": 60,
    "LightGBM": 60,
    "Croston_SBA": 10,
    "MovingAverage_7D": 7,
    "MovingAverage_30D": 30,
    "Naive": 1,
    "SeasonalNaive": 7,
}

MIN_OBSERVATIONS_CONFIG = MIN_OBSERVATIONS


def select_model(quantities: List[float], min_observations_config: Optional[Dict[str, int]] = None) -> str:
    """Legacy backward compatibility model selector."""
    n = len(quantities)
    if n >= 60:
        return "Ridge_LagFeatures"
    elif n >= 7:
        return "MovingAverage_7D"
    return "Naive"

# Requested model name → canonical internal name
MODEL_ALIAS: Dict[str, str] = {
    "prophet": "Prophet",
    "prophet_weekly": "Prophet",
    "prophet_movingavg_ensemble": "Prophet_MovingAvg_Ensemble",
    "moving_avg": "MovingAverage_7D",
    "movingaverage_7d": "MovingAverage_7D",
    "movingaverage_30d": "MovingAverage_30D",
    "naive": "Naive",
    "seasonalnaive": "SeasonalNaive",
    "seasonal_naive": "SeasonalNaive",
    "ridge": "Ridge_LagFeatures",
    "ridge_lagfeatures": "Ridge_LagFeatures",
    "croston": "Croston_SBA",
    "croston_sba": "Croston_SBA",
    "lgbm": "LightGBM",
    "lightgbm": "LightGBM",
}

INDIAN_HOLIDAYS_2024_2026 = {
    # Format: month-day (recurring) or yyyy-mm-dd (one-off)
    "01-26", "08-15", "10-02",  # Republic, Independence, Gandhi
    "2024-04-14", "2024-10-02", "2024-10-12", "2024-10-24",
    "2024-11-15", "2024-12-25",
    "2025-01-26", "2025-03-14", "2025-03-31", "2025-04-14",
    "2025-08-15", "2025-10-02", "2025-10-20", "2025-11-14",
    "2025-12-25",
    "2026-01-26", "2026-03-20", "2026-04-02", "2026-04-14",
    "2026-08-15", "2026-10-02", "2026-10-09", "2026-11-04",
    "2026-12-25",
}


def is_festival(d: date) -> bool:
    md = f"{d.month:02d}-{d.day:02d}"
    ymd = d.isoformat()
    return md in INDIAN_HOLIDAYS_2024_2026 or ymd in INDIAN_HOLIDAYS_2024_2026


# ---------------------------------------------------------------------------
# Data version hash (idempotency key)
# ---------------------------------------------------------------------------

def make_data_version_hash(dataset_id: int, product_id: str, as_of: date) -> str:
    payload = f"{dataset_id}|{product_id}|{as_of.isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def get_latest_upload_job_id(db: Session, dataset_id: int) -> Optional[int]:
    job = (
        db.query(UploadJob.id)
        .filter(UploadJob.status == "COMPLETED")
        .order_by(UploadJob.id.desc())
        .first()
    )
    return job[0] if job else None


def check_historical_warning(as_of: date) -> Dict[str, Any]:
    today = date.today()
    days_behind = (today - as_of).days
    is_historical = days_behind > 90
    return {
        "is_historical": is_historical,
        "as_of": as_of.isoformat(),
        "days_behind": days_behind,
        "message": (
            f"Forecast anchored to historical data through {as_of.isoformat()} "
            f"({days_behind} days ago). Not a real-time projection."
            if is_historical else None
        ),
    }


def adi_cv2(quantities: List[float]) -> Tuple[float, float]:
    """Average Demand Interval and squared Coefficient of Variation for non-zero demand."""
    arr = np.array(quantities, dtype=float)
    non_zero = arr[arr > 0]
    if len(non_zero) < 2:
        return float("inf"), 0.0
    # ADI = total periods / count of non-zero periods
    adi = len(arr) / len(non_zero)
    cv2 = (float(np.std(non_zero, ddof=1)) / float(np.mean(non_zero))) ** 2
    return round(adi, 3), round(cv2, 3)


def classify_sku(quantities: List[float]) -> str:
    """
    Standard Syntetos-Boylan classification:
    - Smooth: ADI <= 1.32 and CV2 <= 0.49
    - Intermittent: ADI > 1.32 and CV2 <= 0.49
    - Erratic: ADI <= 1.32 and CV2 > 0.49
    - Lumpy: ADI > 1.32 and CV2 > 0.49
    """
    adi, cv2 = adi_cv2(quantities)
    if adi > 1.32 and cv2 <= 0.49:
        return "intermittent"
    elif adi > 1.32 and cv2 > 0.49:
        return "lumpy"
    elif cv2 > 0.49:
        return "erratic"
    return "smooth"


# ---------------------------------------------------------------------------
# Forecast models (deterministic point forecasts per day)
# ---------------------------------------------------------------------------

def _dow_weights(quantities: List[float], dates: List[date]) -> Dict[int, float]:
    """Compute per-weekday multiplicative factor relative to global mean."""
    if len(quantities) < 14:
        return {d: 1.0 for d in range(7)}
    arr = np.array(quantities, dtype=float)
    global_mean = float(np.mean(arr)) if float(np.mean(arr)) > 0 else 1.0
    sums: Dict[int, List[float]] = defaultdict(list)
    for q, d in zip(quantities, dates):
        sums[d.weekday()].append(q)
    weights: Dict[int, float] = {}
    for dow in range(7):
        if sums[dow]:
            weights[dow] = max(0.01, float(np.mean(sums[dow])) / global_mean)
        else:
            weights[dow] = 1.0
    return weights


def forecast_seasonal_naive(
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
) -> List[Dict[str, Any]]:
    """Seasonal Naive: same weekday value from last week (+ DOW widened intervals)."""
    n = len(quantities)
    dow_weights = _dow_weights(quantities, dates)
    residuals = []
    for i in range(7, n):
        err = quantities[i] - quantities[i - 7]
        residuals.append(err)
    std_base = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(quantities, ddof=1)) if n > 1 else 1.0

    points = []
    for step in range(1, horizon_days + 1):
        f_date = as_of + timedelta(days=step)
        # Last observed same weekday
        dow = f_date.weekday()
        same_dow_vals = [quantities[i] for i, d in enumerate(dates) if d.weekday() == dow]
        if same_dow_vals:
            yhat = same_dow_vals[-1]
        elif quantities:
            yhat = quantities[-1] * dow_weights.get(dow, 1.0)
        else:
            yhat = 0.0
        # Interval widens with √step (uncertainty grows)
        sigma = std_base * math.sqrt(step)
        points.append({
            "date": f_date.isoformat(),
            "yhat": round(max(0.0, yhat), 2),
            "q05": round(max(0.0, yhat - 1.645 * sigma), 2),
            "q25": round(max(0.0, yhat - 0.674 * sigma), 2),
            "q50": round(max(0.0, yhat), 2),
            "q75": round(max(0.0, yhat + 0.674 * sigma), 2),
            "q95": round(max(0.0, yhat + 1.645 * sigma), 2),
            "is_festival": is_festival(f_date),
            "step": step,
        })
    return points


def forecast_naive(
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
) -> List[Dict[str, Any]]:
    """Naive: repeat last observed value, bands based on recent variance."""
    last = quantities[-1] if quantities else 0.0
    std_base = float(np.std(quantities[-14:], ddof=1)) if len(quantities) > 2 else abs(last) * 0.3 + 1
    points = []
    for step in range(1, horizon_days + 1):
        f_date = as_of + timedelta(days=step)
        sigma = std_base * math.sqrt(step)
        points.append({
            "date": f_date.isoformat(),
            "yhat": round(max(0.0, last), 2),
            "q05": round(max(0.0, last - 1.645 * sigma), 2),
            "q25": round(max(0.0, last - 0.674 * sigma), 2),
            "q50": round(max(0.0, last), 2),
            "q75": round(max(0.0, last + 0.674 * sigma), 2),
            "q95": round(max(0.0, last + 1.645 * sigma), 2),
            "is_festival": is_festival(f_date),
            "step": step,
        })
    return points


def forecast_moving_average(
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
    window: int = 7,
) -> List[Dict[str, Any]]:
    """Moving Average with DOW adjustment and √horizon widening."""
    arr = np.array(quantities[-max(window, 14):], dtype=float)
    ma = float(np.mean(arr[-window:])) if len(arr) >= window else float(np.mean(arr))
    dow_weights = _dow_weights(quantities, dates)
    residuals = []
    for i in range(window, len(quantities)):
        pred = float(np.mean(quantities[i - window:i]))
        residuals.append(quantities[i] - pred)
    std_base = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(arr, ddof=1))

    points = []
    for step in range(1, horizon_days + 1):
        f_date = as_of + timedelta(days=step)
        dow = f_date.weekday()
        yhat = ma * dow_weights.get(dow, 1.0)
        sigma = std_base * math.sqrt(step)
        points.append({
            "date": f_date.isoformat(),
            "yhat": round(max(0.0, yhat), 2),
            "q05": round(max(0.0, yhat - 1.645 * sigma), 2),
            "q25": round(max(0.0, yhat - 0.674 * sigma), 2),
            "q50": round(max(0.0, yhat), 2),
            "q75": round(max(0.0, yhat + 0.674 * sigma), 2),
            "q95": round(max(0.0, yhat + 1.645 * sigma), 2),
            "is_festival": is_festival(f_date),
            "step": step,
        })
    return points


def forecast_ridge_lag(
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
) -> List[Dict[str, Any]]:
    """
    Ridge regression with lag + calendar features.
    Direct multi-horizon: one prediction per step, not recursive.
    Features: lag_1..7, lag_14, lag_28, dow (one-hot), is_festival, trend.
    """
    try:
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        # Fallback to moving average if sklearn unavailable
        return forecast_moving_average(quantities, dates, horizon_days, as_of)

    n = len(quantities)
    if n < 60:
        return forecast_moving_average(quantities, dates, horizon_days, as_of)

    arr = np.array(quantities, dtype=float)
    max_lag = 28

    # Build feature matrix (each row = one day being predicted)
    X_rows = []
    y_rows = []
    for i in range(max_lag, n):
        feats = _build_ridge_features(arr, dates, i, max_lag)
        X_rows.append(feats)
        y_rows.append(arr[i])

    if len(X_rows) < 10:
        return forecast_moving_average(quantities, dates, horizon_days, as_of)

    X = np.array(X_rows)
    y = np.array(y_rows)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=10.0)
    model.fit(X_scaled, y)

    # Direct multi-horizon: predict each future step independently
    # using available actual lags (pads with mean for unavailable)
    mean_val = float(np.mean(arr[-30:]))
    residuals_insample = y - model.predict(X_scaled)
    std_base = float(np.std(residuals_insample, ddof=1)) if len(residuals_insample) > 1 else mean_val * 0.2

    points = []
    for step in range(1, horizon_days + 1):
        f_date = as_of + timedelta(days=step)
        # For lags that fall in the future, use mean_val as placeholder
        extended = list(arr) + [mean_val] * step
        ext_dates = list(dates) + [as_of + timedelta(days=s) for s in range(1, step + 1)]
        feats = _build_ridge_features(np.array(extended), ext_dates, len(extended) - 1, max_lag)
        feats_scaled = scaler.transform([feats])
        yhat = float(model.predict(feats_scaled)[0])
        sigma = std_base * math.sqrt(step)
        points.append({
            "date": f_date.isoformat(),
            "yhat": round(max(0.0, yhat), 2),
            "q05": round(max(0.0, yhat - 1.645 * sigma), 2),
            "q25": round(max(0.0, yhat - 0.674 * sigma), 2),
            "q50": round(max(0.0, yhat), 2),
            "q75": round(max(0.0, yhat + 0.674 * sigma), 2),
            "q95": round(max(0.0, yhat + 1.645 * sigma), 2),
            "is_festival": is_festival(f_date),
            "step": step,
        })
    return points


def _build_ridge_features(arr: np.ndarray, dates: List[date], idx: int, max_lag: int) -> List[float]:
    """Build feature vector for position idx."""
    d = dates[idx]
    # Lag features
    lags = [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]
    feats = []
    for lag in lags:
        pos = idx - lag
        feats.append(float(arr[pos]) if pos >= 0 else float(np.mean(arr[:max(1, idx)])))
    # Calendar features
    feats.append(float(d.weekday()))  # 0=Mon..6=Sun
    # DOW one-hot
    for dow in range(7):
        feats.append(1.0 if d.weekday() == dow else 0.0)
    feats.append(float(d.month))
    feats.append(1.0 if is_festival(d) else 0.0)
    feats.append(float(idx) / max(1, len(arr)))  # linear trend
    return feats


def forecast_croston(
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
) -> List[Dict[str, Any]]:
    """Croston/SBA for intermittent demand."""
    arr = np.array(quantities, dtype=float)
    non_zero = arr[arr > 0]
    non_zero_idx = np.where(arr > 0)[0]

    if len(non_zero) < 2:
        return forecast_naive(quantities, dates, horizon_days, as_of)

    alpha = 0.1  # smoothing factor
    # Croston decomposition
    a_hat = float(non_zero[-1])  # demand size estimate
    p_hat = float(np.mean(np.diff(non_zero_idx))) if len(non_zero_idx) > 1 else 1.0  # inter-arrival

    for i in range(1, len(non_zero)):
        a_hat = alpha * non_zero[i] + (1 - alpha) * a_hat
    # SBA correction
    sba_rate = (1 - alpha / 2) * (a_hat / max(p_hat, 1.0))

    # Bootstrap intervals
    rng = np.random.default_rng(42)
    p_arrival = 1.0 / max(p_hat, 1.0)
    std_size = float(np.std(non_zero, ddof=1)) if len(non_zero) > 1 else float(a_hat * 0.5)

    points = []
    for step in range(1, horizon_days + 1):
        f_date = as_of + timedelta(days=step)
        # Simulate demand occurrence for this day
        sim = rng.binomial(1, min(1.0, p_arrival), size=2000) * rng.normal(a_hat, std_size, size=2000)
        sim = np.maximum(0.0, sim)
        q05, q25, q75, q95 = np.percentile(sim, [5, 25, 75, 95])
        points.append({
            "date": f_date.isoformat(),
            "yhat": round(sba_rate, 2),
            "q05": round(float(q05), 2),
            "q25": round(float(q25), 2),
            "q50": round(sba_rate, 2),
            "q75": round(float(q75), 2),
            "q95": round(float(q95), 2),
            "is_festival": is_festival(f_date),
            "step": step,
        })
    return points


def dispatch_model(
    model_name: str,
    quantities: List[float],
    dates: List[date],
    horizon_days: int,
    as_of: date,
) -> List[Dict[str, Any]]:
    """Route to the correct model implementation."""
    if model_name in ("SeasonalNaive",):
        return forecast_seasonal_naive(quantities, dates, horizon_days, as_of)
    elif model_name == "Naive":
        return forecast_naive(quantities, dates, horizon_days, as_of)
    elif model_name in ("MovingAverage_7D", "MovingAverage_30D"):
        window = 30 if "30D" in model_name else 7
        return forecast_moving_average(quantities, dates, horizon_days, as_of, window=window)
    elif model_name == "Ridge_LagFeatures":
        return forecast_ridge_lag(quantities, dates, horizon_days, as_of)
    elif model_name == "Croston_SBA":
        return forecast_croston(quantities, dates, horizon_days, as_of)
    # Prophet / LightGBM: fall back to Ridge (actual Prophet requires separate install)
    elif model_name in ("Prophet", "Prophet_Weekly", "Prophet_MovingAvg_Ensemble", "LightGBM"):
        return forecast_ridge_lag(quantities, dates, horizon_days, as_of)
    else:
        return forecast_moving_average(quantities, dates, horizon_days, as_of)


# ---------------------------------------------------------------------------
# Metric calculation functions (no leakage, traceable)
# ---------------------------------------------------------------------------

def wape(actual: Any, predicted: Any) -> Optional[float]:
    """Weighted Absolute Percentage Error (WAPE) expressed as a percentage [0..100+]."""
    act = np.array(actual, dtype=float)
    pred = np.array(predicted, dtype=float)
    tot = float(np.sum(act))
    if tot <= 0:
        return None
    return float(np.sum(np.abs(act - pred)) / tot * 100.0)


def mae(actual: Any, predicted: Any) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(np.array(actual, dtype=float) - np.array(predicted, dtype=float))))


def rmse(actual: Any, predicted: Any) -> float:
    """Root Mean Squared Error."""
    err = np.array(actual, dtype=float) - np.array(predicted, dtype=float)
    return float(np.sqrt(np.mean(err ** 2)))


def bias(actual: Any, predicted: Any) -> float:
    """Mean signed error: positive means over-forecasting, negative means under-forecasting."""
    return float(np.mean(np.array(predicted, dtype=float) - np.array(actual, dtype=float)))


def pinball_loss(actual: Any, predicted_q: Any, q: float) -> float:
    """Pinball loss for quantile q in (0, 1)."""
    act = np.array(actual, dtype=float)
    pred = np.array(predicted_q, dtype=float)
    err = act - pred
    loss = np.maximum(q * err, (q - 1.0) * err)
    return float(np.mean(loss))


def coverage_score(actual: Any, lower: Any, upper: Any) -> float:
    """Empirical percentage of actual observations falling in [lower, upper]."""
    act = np.array(actual, dtype=float)
    low = np.array(lower, dtype=float)
    up = np.array(upper, dtype=float)
    if len(act) == 0:
        return 0.0
    return float(np.mean((act >= low) & (act <= up)) * 100.0)


# ---------------------------------------------------------------------------
# Walk-forward backtest (no leakage)
# ---------------------------------------------------------------------------

def walkforward_backtest(
    quantities: List[float],
    dates: List[date],
    model_name: str,
    horizon_days: int,
    n_folds: int = 4,
) -> Dict[str, Any]:
    """
    Chronological walk-forward backtest.
    Each fold: train on [0, split_point), evaluate on [split_point, split_point+horizon_days).
    Returns per-model metrics with NO data leakage (train max < test min guaranteed).
    """
    n = len(quantities)
    min_train = max(MIN_OBSERVATIONS.get(model_name, 14), 14)

    # Ensure we have enough data
    if n < min_train + horizon_days:
        return {
            "wape": None, "mae": None, "rmse": None, "bias": None,
            "coverage_50": None, "coverage_90": None,
            "folds_used": 0, "error": "insufficient_data",
        }

    # Set up fold boundaries: split points spread across the second half of data
    usable = n - horizon_days
    fold_results = []

    for fold_i in range(n_folds):
        # Calculate split: earlier folds use less data, later folds more
        # split_frac goes from 0.5 to 0.9 across folds
        split_frac = 0.5 + (fold_i / max(1, n_folds - 1)) * 0.4
        split = max(min_train, int(n * split_frac))
        split = min(split, usable - 1)

        train_q = quantities[:split]
        train_d = dates[:split]
        test_start = split
        test_end = min(split + horizon_days, n)

        test_q = quantities[test_start:test_end]
        test_d = dates[test_start:test_end]

        if not test_q:
            continue

        # Double-check no leakage
        if train_d[-1] >= test_d[0]:
            continue  # skip this fold if dates overlap

        as_of = train_d[-1]
        try:
            preds = dispatch_model(model_name, train_q, train_d, len(test_q), as_of)
        except Exception:
            continue

        if len(preds) < len(test_q):
            continue

        actual = np.array(test_q, dtype=float)
        predicted = np.array([p["yhat"] for p in preds[:len(test_q)]], dtype=float)
        q05s = np.array([p.get("q05", predicted[i]) for i, p in enumerate(preds[:len(test_q)])], dtype=float)
        q25s = np.array([p.get("q25", predicted[i]) for i, p in enumerate(preds[:len(test_q)])], dtype=float)
        q75s = np.array([p.get("q75", predicted[i]) for i, p in enumerate(preds[:len(test_q)])], dtype=float)
        q95s = np.array([p.get("q95", predicted[i]) for i, p in enumerate(preds[:len(test_q)])], dtype=float)

        errors = np.abs(actual - predicted)
        signed_errors = predicted - actual  # positive = over-forecast

        total_actual = float(np.sum(actual))
        wape = float(np.sum(errors) / total_actual * 100) if total_actual > 0 else None
        mae = float(np.mean(errors))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        bias = float(np.mean(signed_errors))

        # Interval coverage
        in_50 = float(np.mean((actual >= q25s) & (actual <= q75s)) * 100)
        in_90 = float(np.mean((actual >= q05s) & (actual <= q95s)) * 100)

        fold_results.append({
            "fold": fold_i,
            "wape": wape,
            "mae": mae,
            "rmse": rmse,
            "bias": bias,
            "coverage_50": in_50,
            "coverage_90": in_90,
            "n_test": len(test_q),
        })

    if not fold_results:
        return {
            "wape": None, "mae": None, "rmse": None, "bias": None,
            "coverage_50": None, "coverage_90": None,
            "folds_used": 0, "error": "all_folds_failed",
        }

    # Aggregate: use median across folds to be robust to outlier folds
    def median_metric(key):
        vals = [f[key] for f in fold_results if f.get(key) is not None]
        return round(float(np.median(vals)), 3) if vals else None

    return {
        "wape": median_metric("wape"),
        "mae": median_metric("mae"),
        "rmse": median_metric("rmse"),
        "bias": median_metric("bias"),
        "coverage_50": median_metric("coverage_50"),
        "coverage_90": median_metric("coverage_90"),
        "folds_used": len(fold_results),
    }


# ---------------------------------------------------------------------------
# Champion selection with baseline guard
# ---------------------------------------------------------------------------

def select_champion(
    model_metrics: Dict[str, Dict[str, Any]],
    baseline_model: str = "SeasonalNaive",
    improvement_threshold_pct: float = 5.0,
) -> Tuple[Optional[str], str, float]:
    """
    Picks champion = lowest median WAPE.
    CRITICAL RULE: The leaderboard NEVER shows a champion unless at least two models actually ran.
    If champion does not beat SeasonalNaive by >= 5%, recommend SeasonalNaive.
    Returns (champion_name, effective_recommendation, improvement_pct).
    """
    # Filter to models with a valid WAPE
    valid = {k: v for k, v in model_metrics.items() if v.get("wape") is not None}
    if len(valid) < 2:
        fallback = next(iter(valid.keys())) if valid else baseline_model
        return None, fallback, 0.0

    champion = min(valid, key=lambda k: valid[k]["wape"])
    champ_wape = valid[champion]["wape"]
    baseline_wape = valid.get(baseline_model, {}).get("wape")

    if baseline_wape is None:
        return champion, champion, 0.0

    improvement = (baseline_wape - champ_wape) / baseline_wape * 100

    if improvement < improvement_threshold_pct:
        return champion, baseline_model, improvement
    return champion, champion, improvement


# ---------------------------------------------------------------------------
# Confidence rating (transparent rule)
# ---------------------------------------------------------------------------

def compute_confidence(
    n_obs: int,
    champion_wape: Optional[float],
    seasonal_naive_wape: Optional[float],
    coverage_90: Optional[float],
    sku_type: str,
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Returns (rating, reasons_list).
    Rating: HIGH / MEDIUM / LOW based on transparent rules.
    """
    score = 0
    reasons = []

    if n_obs >= 365:
        score += 3
        reasons.append({"code": "history_long", "text": f"Over a year of sales history ({n_obs} days) available."})
    elif n_obs >= 180:
        score += 2
        reasons.append({"code": "history_medium", "text": f"We have about {n_obs // 30} months of sales history for this item."})
    elif n_obs >= 90:
        score += 1
        reasons.append({"code": "history_short", "text": f"Only {n_obs} days of sales history — more data will improve accuracy."})
    else:
        reasons.append({"code": "history_very_short", "text": f"Only {n_obs} days of history. Forecast reliability is limited."})

    if champion_wape is not None and seasonal_naive_wape is not None:
        improvement = (seasonal_naive_wape - champion_wape) / max(seasonal_naive_wape, 0.01) * 100
        if improvement >= 20:
            score += 3
        elif improvement >= 5:
            score += 2
        else:
            score += 0
            reasons.append({"code": "low_improvement", "text": "The best forecasting method is only slightly better than a simple 'same as last week' guess."})

    if coverage_90 is not None:
        coverage_error = abs(coverage_90 - 90.0)
        if coverage_error <= 5:
            score += 2
        elif coverage_error <= 15:
            score += 1
        else:
            reasons.append({"code": "poor_coverage", "text": "The predicted range does not reliably capture actual sales."})

    if sku_type in ("intermittent", "lumpy"):
        score = max(0, score - 1)
        reasons.append({"code": "intermittent", "text": "This item only sells on some days, making it harder to predict precisely."})

    if score >= 7:
        rating = "HIGH"
    elif score >= 4:
        rating = "MEDIUM"
    else:
        rating = "LOW"

    return rating, reasons


# ---------------------------------------------------------------------------
# Inventory recommendation
# ---------------------------------------------------------------------------

def compute_inventory_recommendation(
    quantities: List[float],
    daily_forecast: List[Dict[str, Any]],
    service_level: float = 0.95,
    lead_time_days: int = 7,
    current_stock: Optional[float] = None,
    is_simulated: bool = True,
) -> Dict[str, Any]:
    """Compute reorder point, safety stock, suggested order qty."""
    if not quantities:
        return {}

    lead_time_days = max(1, int(lead_time_days))
    horizon_demand = sum(p["q50"] for p in daily_forecast)
    daily_mean = float(np.mean(quantities[-30:])) if quantities else 0.0

    # Safety stock via empirical lead-time demand quantile
    rng = np.random.default_rng(42)
    arr = np.array(quantities, dtype=float)
    sim_draws = rng.choice(arr, size=(3000, max(1, lead_time_days)), replace=True)
    lead_time_sums = np.sum(sim_draws, axis=1)
    lead_time_quantile = float(np.percentile(lead_time_sums, service_level * 100))
    expected_lead_time_demand = lead_time_days * daily_mean
    safety_stock = max(0.0, lead_time_quantile - expected_lead_time_demand)

    reorder_point = round(expected_lead_time_demand + safety_stock, 1)
    suggest_order_qty = round(horizon_demand + safety_stock, 1)
    stockout_risk_days = (current_stock / max(daily_mean, 0.1)) if current_stock is not None else None

    if stockout_risk_days is not None:
        if stockout_risk_days < lead_time_days:
            stockout_risk = "HIGH"
        elif stockout_risk_days < lead_time_days + 7:
            stockout_risk = "MEDIUM"
        else:
            stockout_risk = "LOW"
    else:
        stockout_risk = "MEDIUM"

    if is_simulated:
        assumptions = [
            f"Lead time: {lead_time_days} days (simulated — not from your actual supplier data)",
            f"Service level: {int(service_level * 100)}% (probability of not running out)",
            f"Safety stock calculated from {len(quantities)} historical demand observations",
        ]
        if current_stock is None:
            assumptions.append("Current stock level: not uploaded — using estimates only")
    else:
        assumptions = [
            f"Lead time: {lead_time_days} days (configured from supplier parameters)",
            f"Service level: {int(service_level * 100)}% (target non-stockout probability)",
            f"Safety stock calculated from {len(quantities)} historical demand observations",
        ]
        if current_stock is not None:
            assumptions.append(f"Current stock level: {round(current_stock, 1):g} units (verified on-hand stock)")
        else:
            assumptions.append("Current stock level: not specified")

    return {
        "reorder_point": reorder_point,
        "suggest_order_qty": suggest_order_qty,
        "safety_stock": round(safety_stock, 1),
        "expected_demand_in_horizon": round(horizon_demand, 1),
        "daily_mean": round(daily_mean, 2),
        "service_level": service_level,
        "lead_time_days": lead_time_days,
        "current_stock": current_stock,
        "stockout_risk": stockout_risk,
        "assumptions": assumptions,
        "data_source": "simulated" if is_simulated else "configured",
    }


# ---------------------------------------------------------------------------
# Main summary function: runs all eligible models and returns unified response
# ---------------------------------------------------------------------------

def compute_forecast_summary(
    db: Session,
    dataset_id: int,
    product_id: str,
    horizon_days: int = 7,
    force_recompute: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes or returns cached forecast summary for a SKU.
    Runs ALL eligible models independently.
    Ineligible models → status='skipped' with plain reason.
    Idempotent: won't re-run if (sku, horizon, model, data_version_hash) exists.
    """
    # 1. Fetch history aggregated by date across cities
    daily_records = (
        db.query(
            DailyProductDemand.date_,
            func.sum(DailyProductDemand.total_quantity).label("total_qty"),
        )
        .filter(
            DailyProductDemand.dataset_id == dataset_id,
            DailyProductDemand.product_id == str(product_id),
        )
        .group_by(DailyProductDemand.date_)
        .order_by(DailyProductDemand.date_.asc())
        .all()
    )

    if not daily_records:
        return {
            "status": "not_found",
            "message": f"No sales found for SKU {product_id} in dataset {dataset_id}. Upload sales data to get started.",
        }

    quantities = [float(r.total_qty or 0.0) for r in daily_records]
    dates = [r.date_ for r in daily_records]
    n_obs = len(quantities)
    as_of = dates[-1]
    data_version_hash = make_data_version_hash(dataset_id, product_id, as_of)

    # 2. Load product metadata
    product = db.query(Product).filter(Product.product_id == str(product_id)).first()
    product_info = {
        "product_id": str(product_id),
        "name": product.product_name if product else f"SKU {product_id}",
        "category": product.l1_category or product.l0_category or "Unknown" if product else "Unknown",
        "brand": product.brand_name if product else None,
        "unit": product.unit if product else None,
    }

    # 3. SKU classification
    adi, cv2 = adi_cv2(quantities)
    sku_type = classify_sku(quantities)

    # 4. All candidate models to evaluate
    CANDIDATE_MODELS = ["Naive", "SeasonalNaive", "MovingAverage_7D", "Ridge_LagFeatures"]
    if sku_type in ("intermittent", "lumpy"):
        CANDIDATE_MODELS.append("Croston_SBA")

    # 5. Run each model (or look up existing run)
    model_results: Dict[str, Dict[str, Any]] = {}
    all_run_rows: List[Dict[str, Any]] = {}

    for model_name in CANDIDATE_MODELS:
        min_req = MIN_OBSERVATIONS.get(model_name, 1)
        if model_name == "Croston_SBA":
            n_nonzero = len([q for q in quantities if q > 0])
            eligible = n_nonzero >= min_req
            skip_reason_text = f"Croston/SBA needs at least {min_req} non-zero sales days; this item has {n_nonzero}." if not eligible else None
        else:
            eligible = n_obs >= min_req
            skip_reason_text = f"{model_name} needs at least {min_req} days of history; this item has only {n_obs} days." if not eligible else None

        if not eligible:
            _upsert_run(
                db=db,
                dataset_id=dataset_id,
                product_id=product_id,
                model_name=model_name,
                model_requested=model_name,
                horizon_days=horizon_days,
                status="SKIPPED",
                skip_reason=skip_reason_text,
                data_version_hash=data_version_hash,
                history_obs_count=n_obs,
                job_id=job_id,
                metrics={},
                future_points=[],
                as_of=as_of,
            )
            all_run_rows[model_name] = {
                "name": model_name,
                "status": "skipped",
                "skip_reason": skip_reason_text,
                "wape": None, "mae": None, "rmse": None, "bias": None,
            }
            continue

        # Check if a fresh run already exists (idempotency)
        existing_run = _find_existing_run(db, dataset_id, product_id, model_name, horizon_days, data_version_hash)
        has_valid_cached_metrics = False
        if existing_run and existing_run.metrics_summary:
            try:
                m_check = json.loads(existing_run.metrics_summary)
                if m_check.get("wape") is not None:
                    has_valid_cached_metrics = True
            except Exception:
                pass

        if existing_run and not force_recompute and has_valid_cached_metrics:
            metrics = {}
            if existing_run.metrics_summary:
                try:
                    metrics = json.loads(existing_run.metrics_summary)
                except Exception:
                    pass
            # Load forecast items
            items = (
                db.query(ForecastItem)
                .filter(ForecastItem.run_id == existing_run.id)
                .order_by(ForecastItem.forecast_date.asc())
                .all()
            )
            future_points = [
                {
                    "date": it.forecast_date.isoformat(),
                    "yhat": it.predicted_demand,
                    "q05": it.quantiles.get("q05") if it.quantiles else None,
                    "q25": it.quantiles.get("q25") if it.quantiles else None,
                    "q50": it.quantiles.get("q50", it.predicted_demand) if it.quantiles else it.predicted_demand,
                    "q75": it.quantiles.get("q75") if it.quantiles else None,
                    "q95": it.quantiles.get("q95") if it.quantiles else None,
                    "is_festival": is_festival(it.forecast_date),
                    "step": (it.forecast_date - as_of).days,
                }
                for it in items
            ]
            model_results[model_name] = {"metrics": metrics, "future_points": future_points, "run_id": existing_run.id}
            all_run_rows[model_name] = {
                "name": model_name,
                "status": "complete",
                "skip_reason": None,
                "wape": metrics.get("wape"),
                "mae": metrics.get("mae"),
                "rmse": metrics.get("rmse"),
                "bias": metrics.get("bias"),
            }
            continue

        # Compute fresh run
        try:
            future_points = dispatch_model(model_name, quantities, dates, horizon_days, as_of)
            bt = walkforward_backtest(quantities, dates, model_name, horizon_days, n_folds=4)
        except Exception as exc:
            skip_reason_text = f"{model_name} failed: {str(exc)[:120]}"
            _upsert_run(
                db=db, dataset_id=dataset_id, product_id=product_id,
                model_name=model_name, model_requested=model_name,
                horizon_days=horizon_days, status="FAILED",
                skip_reason=skip_reason_text, data_version_hash=data_version_hash,
                history_obs_count=n_obs, job_id=job_id,
                metrics={}, future_points=[], as_of=as_of,
            )
            all_run_rows[model_name] = {
                "name": model_name, "status": "failed",
                "skip_reason": skip_reason_text,
                "wape": None, "mae": None, "rmse": None, "bias": None,
            }
            continue

        metrics = {
            "wape": bt["wape"],
            "mae": bt["mae"],
            "rmse": bt["rmse"],
            "bias": bt["bias"],
            "coverage_50": bt.get("coverage_50"),
            "coverage_90": bt.get("coverage_90"),
            "folds_used": bt.get("folds_used", 0),
        }

        run_id = _upsert_run(
            db=db, dataset_id=dataset_id, product_id=product_id,
            model_name=model_name, model_requested=model_name,
            horizon_days=horizon_days, status="COMPLETED",
            skip_reason=None, data_version_hash=data_version_hash,
            history_obs_count=n_obs, job_id=job_id,
            metrics=metrics, future_points=future_points, as_of=as_of,
        )

        model_results[model_name] = {"metrics": metrics, "future_points": future_points, "run_id": run_id}
        all_run_rows[model_name] = {
            "name": model_name, "status": "complete",
            "skip_reason": None,
            "wape": bt["wape"], "mae": bt["mae"], "rmse": bt["rmse"], "bias": bt["bias"],
        }

    # 6. Champion selection
    wape_by_model = {k: v["metrics"]["wape"] for k, v in model_results.items() if v["metrics"].get("wape") is not None}
    champion_name, recommended_model, improvement_pct = select_champion(
        {k: {"wape": w} for k, w in wape_by_model.items()},
        baseline_model="SeasonalNaive",
        improvement_threshold_pct=5.0,
    )

    # 7. Pick champion forecast points
    if recommended_model in model_results:
        champion_points = model_results[recommended_model]["future_points"]
    elif model_results:
        first = next(iter(model_results.values()))
        champion_points = first["future_points"]
    else:
        # All models skipped — use seasonal naive anyway
        champion_points = forecast_seasonal_naive(quantities, dates, horizon_days, as_of)

    # 8. Headline numbers
    total_expected = round(sum(p.get("q50", p.get("yhat", 0)) for p in champion_points), 1)
    likely_low = round(sum(p.get("q25", p.get("yhat", 0)) for p in champion_points), 1)
    likely_high = round(sum(p.get("q75", p.get("yhat", 0)) for p in champion_points), 1)

    # 9. Confidence
    champ_wape = wape_by_model.get(champion_name)
    naive_wape = wape_by_model.get("SeasonalNaive")
    cov_90 = model_results.get(recommended_model, {}).get("metrics", {}).get("coverage_90")
    confidence_rating, confidence_reasons = compute_confidence(
        n_obs=n_obs,
        champion_wape=champ_wape,
        seasonal_naive_wape=naive_wape,
        coverage_90=cov_90,
        sku_type=sku_type,
    )

    # 10. History for chart (last 60 days)
    history_window = daily_records[-60:]
    history = [
        {"date": r.date_.isoformat(), "units": float(r.total_qty or 0.0)}
        for r in history_window
    ]

    # 11. Inventory recommendation
    from backend.models.procurement import SupplierProduct
    from backend.models.inventory import LeadTimeObservation, InventoryState

    sp = (
        db.query(SupplierProduct)
        .filter(SupplierProduct.product_id == str(product_id))
        .order_by(SupplierProduct.is_preferred.desc(), SupplierProduct.id.asc())
        .first()
    )

    lto = (
        db.query(LeadTimeObservation)
        .filter(
            LeadTimeObservation.dataset_id == dataset_id,
            LeadTimeObservation.product_id == str(product_id),
        )
        .order_by(LeadTimeObservation.created_at.desc())
        .first()
    )

    inv = (
        db.query(InventoryState)
        .filter(
            InventoryState.dataset_id == dataset_id,
            InventoryState.product_id == str(product_id),
        )
        .order_by(InventoryState.snapshot_date.desc(), InventoryState.id.desc())
        .first()
    )

    configured_lead_time = None
    is_lead_time_simulated = True
    if sp and sp.promised_lead_time_days:
        configured_lead_time = sp.promised_lead_time_days
        is_lead_time_simulated = False
    elif lto and lto.actual_days:
        configured_lead_time = lto.actual_days
        is_lead_time_simulated = False

    effective_lead_time = configured_lead_time if configured_lead_time is not None else 7

    current_stock_val = None
    if inv and inv.closing_stock is not None:
        current_stock_val = float(inv.closing_stock)

    recommendation = compute_inventory_recommendation(
        quantities=quantities,
        daily_forecast=champion_points,
        service_level=0.95,
        lead_time_days=effective_lead_time,
        current_stock=current_stock_val,
        is_simulated=is_lead_time_simulated,
    )

    # 12. Reliability card
    baseline_wape = wape_by_model.get("SeasonalNaive")
    champion_model_metrics = model_results.get(recommended_model, {}).get("metrics", {})

    # 13. Build improvement_vs_naive and is_champion for each model
    for row in all_run_rows.values():
        row["is_champion"] = bool(champion_name and row.get("name") == champion_name)
        if row.get("wape") is not None and baseline_wape is not None and baseline_wape > 0:
            row["improvement_vs_naive_pct"] = round(
                (baseline_wape - row["wape"]) / baseline_wape * 100, 1
            )
        else:
            row["improvement_vs_naive_pct"] = None

    latest_upload_id = get_latest_upload_job_id(db, dataset_id)

    # Baseline-beat notice
    baseline_notice = None
    if champion_name is None:
        baseline_notice = "Leaderboard requires at least two models to run before selecting a champion."
    elif improvement_pct < 5.0 and champ_wape is not None:
        baseline_notice = (
            f"No complex model beat the simple baseline for this product "
            f"(best improvement was {round(improvement_pct, 1)}% over 'same as last week'). "
            f"Using '{recommended_model}' as the recommended method."
        )

    return {
        "status": "success",
        "sku": product_info,
        "horizon_days": horizon_days,
        "headline": {
            "expected_units": total_expected,
            "likely_low": likely_low,
            "likely_high": likely_high,
            "confidence": confidence_rating,
            "confidence_reasons": confidence_reasons,
        },
        "daily": champion_points,
        "history": history,
        "reliability": {
            "has_champion": champion_name is not None,
            "champion_model": champion_name if champion_name else None,
            "recommended_model": recommended_model,
            "champion_model_raw": champion_name,
            "champion_wape": round(champ_wape, 1) if (champion_name and champ_wape is not None) else None,
            "seasonal_naive_wape": round(baseline_wape, 1) if baseline_wape is not None else None,
            "improvement_pct": round(improvement_pct, 1) if champion_name else 0.0,
            "coverage_90": round(cov_90, 1) if cov_90 is not None else None,
            "coverage_50": round(champion_model_metrics.get("coverage_50") or 0, 1),
            "baseline_notice": baseline_notice,
            "folds_used": champion_model_metrics.get("folds_used"),
        },
        "models": list(all_run_rows.values()),
        "recommendation": recommendation,
        "sku_classification": {
            "type": sku_type,
            "adi": adi,
            "cv2": cv2,
            "n_obs": n_obs,
        },
        "data_version": data_version_hash,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "historical_warning": check_historical_warning(as_of),
        "as_of": as_of.isoformat(),
        "source_upload_job_id": latest_upload_id,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _find_existing_run(
    db: Session,
    dataset_id: int,
    product_id: str,
    model_name: str,
    horizon_days: int,
    data_version_hash: str,
) -> Optional[ForecastRun]:
    """Find an existing COMPLETED run for idempotency."""
    return (
        db.query(ForecastRun)
        .filter(
            ForecastRun.dataset_id == dataset_id,
            ForecastRun.product_id == str(product_id),
            ForecastRun.model_name == model_name,
            ForecastRun.horizon_days == horizon_days,
            ForecastRun.data_version_hash == data_version_hash,
            ForecastRun.status == "COMPLETED",
        )
        .first()
    )


def _upsert_run(
    db: Session,
    dataset_id: int,
    product_id: str,
    model_name: str,
    model_requested: str,
    horizon_days: int,
    status: str,
    skip_reason: Optional[str],
    data_version_hash: str,
    history_obs_count: int,
    job_id: Optional[str],
    metrics: Dict[str, Any],
    future_points: List[Dict[str, Any]],
    as_of: date,
) -> Optional[int]:
    """Upsert a ForecastRun, return run id."""
    now = datetime.now(timezone.utc)

    # Ensure product exists
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

    new_run = ForecastRun(
        dataset_id=dataset_id,
        product_id=str(product_id),
        model_name=model_name,
        model_requested=model_requested,
        horizon_days=horizon_days,
        status=status,
        skip_reason=skip_reason,
        data_version_hash=data_version_hash,
        history_obs_count=history_obs_count,
        job_id=job_id,
        is_stale=False,
        data_date_max=as_of,
        start_date=None,
        end_date=as_of,
        metrics_summary=json.dumps(metrics) if metrics else None,
        completed_at=now if status in ("COMPLETED", "SKIPPED", "FAILED") else None,
    )
    db.add(new_run)
    db.flush()

    # Save ForecastItem rows for future dates
    for pt in future_points:
        pt_date = date.fromisoformat(pt["date"])
        quantile_dict = {k: pt.get(k) for k in ("q05", "q25", "q50", "q75", "q95") if pt.get(k) is not None}
        item = ForecastItem(
            dataset_id=dataset_id,
            run_id=new_run.id,
            product_id=str(product_id),
            city_name="ALL",
            forecast_date=pt_date,
            predicted_demand=pt.get("q50", pt.get("yhat", 0.0)),
            lower_bound=pt.get("q05"),
            upper_bound=pt.get("q95"),
            model_name=model_name,
            quantiles=quantile_dict,
        )
        db.add(item)

    db.commit()
    return new_run.id


# ---------------------------------------------------------------------------
# Legacy compatibility: compute_or_get_forecast (kept for other endpoints)
# ---------------------------------------------------------------------------

def compute_or_get_forecast(
    db: Session,
    dataset_id: int,
    product_id: str,
    city_name: Optional[str] = None,
    horizon_days: int = 14,
    as_of: Optional[date] = None,
    force_recompute: bool = False,
    model_name: str = "SeasonalNaive",
) -> Dict[str, Any]:
    """
    Legacy compatibility wrapper — calls compute_forecast_summary and flattens for old endpoints.
    model_name is now the requested model; it will be run only if eligible.
    """
    result = compute_forecast_summary(
        db=db,
        dataset_id=dataset_id,
        product_id=product_id,
        horizon_days=horizon_days,
        force_recompute=force_recompute,
    )
    if result.get("status") != "success":
        return result

    # Find the model result for the requested model (canonicalized)
    canonical = MODEL_ALIAS.get(model_name.lower(), model_name)
    model_row = next((m for m in result.get("models", []) if m["name"] == canonical), None)

    return {
        **result,
        "status": "success",
        "product_id": str(product_id),
        "city_name": city_name or "ALL",
        "as_of": result.get("as_of"),
        "model_name": canonical,
        "requested_model": model_name,
        "model_fallback_reason": model_row.get("skip_reason") if model_row else None,
        "confidence_tier": result["headline"]["confidence"],
        "predicted_mean": result["headline"]["expected_units"] / max(horizon_days, 1),
        "yhat_mean": result["headline"]["expected_units"] / max(horizon_days, 1),
        "historical_records": result["sku_classification"]["n_obs"],
        "forecast": [
            {
                "date": p["date"],
                "predicted_demand": p.get("q50", p.get("yhat", 0)),
                "yhat": p.get("q50", p.get("yhat", 0)),
                "yhat_lower": p.get("q05"),
                "yhat_upper": p.get("q95"),
                "is_future": True,
            }
            for p in result.get("daily", [])
        ],
        "fan_chart": [
            {
                "date": p["date"],
                "mean": p.get("q50", 0),
                "q05": p.get("q05", 0),
                "q25": p.get("q25", 0),
                "q50": p.get("q50", 0),
                "q75": p.get("q75", 0),
                "q90": p.get("q95", 0),
                "q95": p.get("q95", 0),
            }
            for p in result.get("daily", [])
        ],
        "freshness": {
            "computed_at": result.get("computed_at"),
            "data_through": result.get("as_of"),
            "is_stale": False,
            "model_name": canonical,
            "requested_model": model_name,
            "confidence_tier": result["headline"]["confidence"],
            "model_fallback_reason": model_row.get("skip_reason") if model_row else None,
            "source_upload_job_id": result.get("source_upload_job_id"),
        },
        "quantile_safety_stock": {
            "ss_quantile": result["recommendation"].get("safety_stock"),
            "ss_kings": None,
            "ss_classical": None,
            "delta_vs_kings": None,
            "delta_vs_classical": None,
        },
        "model_metrics": {
            "wape": model_row.get("wape") if model_row else None,
            "mae": model_row.get("mae") if model_row else None,
            "rmse": model_row.get("rmse") if model_row else None,
        } if model_row else {},
    }


def recompute_all_forecasts_for_dataset(
    db: Session,
    dataset_id: int,
    product_ids: Optional[List[str]] = None,
    horizon_days: int = 14,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    if not product_ids:
        rows = (
            db.query(DailyProductDemand.product_id)
            .filter(DailyProductDemand.dataset_id == dataset_id)
            .distinct()
            .all()
        )
        product_ids = [r[0] for r in rows if r[0]]

    recomputed_count = 0
    for pid in product_ids:
        res = compute_forecast_summary(db=db, dataset_id=dataset_id, product_id=pid,
                                       horizon_days=horizon_days, force_recompute=True)
        if res.get("status") == "success":
            recomputed_count += 1

    return {
        "status": "success",
        "dataset_id": dataset_id,
        "recomputed_count": recomputed_count,
        "product_ids": product_ids,
    }
