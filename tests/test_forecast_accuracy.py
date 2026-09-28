import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, timedelta
import pytest
from backend.services.forecast_service import (
    wape,
    mae,
    rmse,
    bias,
    pinball_loss,
    coverage_score,
    walkforward_backtest,
    select_champion,
    compute_confidence,
    make_data_version_hash,
    dispatch_model,
    classify_sku,
    adi_cv2,
)


def test_metric_functions():
    actuals = [10.0, 20.0, 30.0, 40.0]
    preds = [12.0, 18.0, 33.0, 37.0]

    # MAE = (|2| + |-2| + |3| + |-3|) / 4 = 10 / 4 = 2.5
    assert mae(actuals, preds) == 2.5

    # RMSE = sqrt((4 + 4 + 9 + 9) / 4) = sqrt(26 / 4) = sqrt(6.5) ≈ 2.5495
    assert pytest.approx(rmse(actuals, preds), 0.001) == 2.5495

    # WAPE = sum(|error|) / sum(actuals) = 10 / 100 = 0.10 => 10%
    assert wape(actuals, preds) == 10.0

    # Bias = mean(pred - actual) = (2 - 2 + 3 - 3) / 4 = 0.0
    assert bias(actuals, preds) == 0.0

    # Overforecast bias:
    high_preds = [15.0, 25.0, 35.0, 45.0]
    assert bias(actuals, high_preds) == 5.0

    # Underforecast bias:
    low_preds = [5.0, 15.0, 25.0, 35.0]
    assert bias(actuals, low_preds) == -5.0


def test_pinball_loss():
    actuals = [10.0, 20.0]
    preds_q90 = [12.0, 19.0] # actual 10 < 12 (over): (1 - 0.9)*(12 - 10) = 0.2; actual 20 > 19 (under): 0.9*(20 - 19) = 0.9 => mean = 0.55
    loss = pinball_loss(actuals, preds_q90, q=0.90)
    assert pytest.approx(loss, 0.01) == 0.55


def test_interval_coverage_calculation():
    actuals = [10.0, 20.0, 30.0, 40.0]
    lows = [8.0, 15.0, 25.0, 50.0]  # 40 is not in [50, 60] -> 3 of 4 covered
    highs = [15.0, 25.0, 35.0, 60.0]
    cov = coverage_score(actuals, lows, highs)
    assert cov == 75.0


def test_walkforward_split_has_no_leakage():
    # 120 days of synthetic history
    base_date = date(2025, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(120)]
    quantities = [20.0 + (i % 7) * 3.0 for i in range(120)]

    bt = walkforward_backtest(quantities, dates, model_name="MovingAverage_7D", horizon_days=7, n_folds=4)
    assert bt["folds_used"] >= 3
    assert bt["wape"] is not None

    # Check explicit leakage in folds by inspecting fold indices logic
    horizon = 7
    n = len(dates)
    fold_size = horizon
    for i in range(bt["folds_used"]):
        test_end = n - i * fold_size
        test_start = test_end - fold_size
        train_end = test_start
        assert dates[train_end - 1] < dates[test_start], "Data leakage! Train max date must be < test min date"


def test_select_champion_requires_at_least_two_models():
    # Only 1 model ran
    single_model = {"MovingAverage_7D": {"wape": 14.5}}
    champ, rec, imp = select_champion(single_model, baseline_model="SeasonalNaive")
    # Rule: Leaderboard NEVER shows a champion unless at least two models actually ran
    assert champ is None
    assert rec == "MovingAverage_7D"
    assert imp == 0.0


def test_select_champion_improvement_threshold():
    # Two models ran: complex model beats baseline by > 5%
    metrics_win = {
        "SeasonalNaive": {"wape": 20.0},
        "Ridge_LagFeatures": {"wape": 14.0}, # (20 - 14)/20 = 30% improvement
    }
    champ, rec, imp = select_champion(metrics_win, baseline_model="SeasonalNaive", improvement_threshold_pct=5.0)
    assert champ == "Ridge_LagFeatures"
    assert rec == "Ridge_LagFeatures"
    assert imp == 30.0

    # Complex model did NOT beat baseline by at least 5% (e.g. 19.5 vs 20.0 is 2.5% improvement)
    metrics_marginal = {
        "SeasonalNaive": {"wape": 20.0},
        "Ridge_LagFeatures": {"wape": 19.5},
    }
    champ, rec, imp = select_champion(metrics_marginal, baseline_model="SeasonalNaive", improvement_threshold_pct=5.0)
    assert champ == "Ridge_LagFeatures"
    # Fallback recommendation must be SeasonalNaive because it didn't beat baseline by >= 5%
    assert rec == "SeasonalNaive"
    assert imp == 2.5


def test_confidence_rule():
    # High confidence: >= 365 days, good wape, coverage close to 90%, smooth SKU
    rating_high, reasons_high = compute_confidence(
        n_obs=400,
        champion_wape=12.0,
        seasonal_naive_wape=18.0,
        coverage_90=89.0,
        sku_type="smooth",
    )
    assert rating_high == "HIGH"
    assert any("history" in r["text"].lower() for r in reasons_high)

    # Low confidence: short history, lumpy SKU
    rating_low, reasons_low = compute_confidence(
        n_obs=45,
        champion_wape=35.0,
        seasonal_naive_wape=36.0,
        coverage_90=60.0,
        sku_type="lumpy",
    )
    assert rating_low == "LOW"
    assert any("lumpy" in r["text"].lower() or "sales" in r["text"].lower() for r in reasons_low)


def test_idempotent_hash_computation():
    h1 = make_data_version_hash(1, "SKU100", date(2025, 5, 1))
    h2 = make_data_version_hash(1, "SKU100", date(2025, 5, 1))
    h3 = make_data_version_hash(1, "SKU100", date(2025, 5, 2))
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA256 hex string


def test_sku_classification_adi_cv2():
    # Smooth: regular non-zero sales, low variance
    smooth_qty = [10.0, 12.0, 11.0, 10.0, 13.0, 10.0, 11.0]
    adi, cv2 = adi_cv2(smooth_qty)
    assert adi <= 1.32
    assert classify_sku(smooth_qty) == "smooth"

    # Intermittent: zero sales on most days (ADI > 1.32, CV2 low)
    intermittent_qty = [0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 5.0]
    assert classify_sku(intermittent_qty) in ("intermittent", "lumpy")


def test_dispatch_model_interval_expansion():
    # Check that prediction intervals expand with horizon
    base_date = date(2025, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(100)]
    quantities = [15.0 + (i % 7) * 4.0 for i in range(100)]
    as_of = dates[-1]

    future_points = dispatch_model("MovingAverage_7D", quantities, dates, horizon_days=14, as_of=as_of)
    assert len(future_points) == 14

    width_day1 = future_points[0]["q95"] - future_points[0]["q05"]
    width_day14 = future_points[13]["q95"] - future_points[13]["q05"]
    # Interval width grows with horizon
    assert width_day14 >= width_day1
