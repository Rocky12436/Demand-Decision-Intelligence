import pytest
import numpy as np
from datetime import date, timedelta

from backend.services.anomaly_service import (
    classify_sbc,
    compute_modified_z_score,
    detect_anomalies_for_series,
    fit_count_model_p99,
)


def test_synthetic_intermittent_sku_generates_zero_spike_anomalies():
    """
    Acceptance Criterion:
    A synthetic SKU selling on 3 of every 14 days generates zero SPIKE anomalies under normal behaviour.
    """
    # 60 days total: pattern of 3 sales per 14-day cycle (e.g. sale on day 0, 4, 9, 14, 18, 23, ...)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(70)]
    quantities = []
    for i in range(70):
        day_in_cycle = i % 14
        if day_in_cycle in (0, 5, 10):
            # Normal sale size between 8 and 12 units
            quantities.append(10.0 + (i % 3))
        else:
            quantities.append(0.0)

    res = detect_anomalies_for_series(
        product_id="INTERMITTENT-SKU",
        city_name="Delhi",
        dates=dates,
        quantities=quantities,
        min_observations=30
    )

    # Must be classified as INTERMITTENT or LUMPY
    assert res["sbc_class"] in ("INTERMITTENT", "LUMPY")
    # Must NOT produce false-positive spikes on zero days or normal intermittent sales
    spike_anomalies = [a for a in res["anomalies"] if a["anomaly_type"] == "SPIKE"]
    assert len(spike_anomalies) == 0, f"Expected 0 spikes, but got {len(spike_anomalies)}"


def test_division_by_zero_impossible_property_test():
    """
    Acceptance Criterion:
    Division-by-zero is impossible; property test with sigma == 0 and MAD == 0.
    """
    # Constant non-zero values (all 15.0) -> std = 0, MAD = 0
    constant_dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(40)]
    constant_quantities = [15.0] * 40

    res_constant = detect_anomalies_for_series(
        product_id="CONSTANT-SKU",
        city_name="ALL",
        dates=constant_dates,
        quantities=constant_quantities
    )
    assert res_constant["status"] == "COMPLETED"
    assert len(res_constant["anomalies"]) == 0

    # All zeros (all 0.0) -> std = 0, MAD = 0
    zero_quantities = [0.0] * 40
    res_zero = detect_anomalies_for_series(
        product_id="ZERO-SKU",
        city_name="ALL",
        dates=constant_dates,
        quantities=zero_quantities
    )
    assert res_zero["status"] == "COMPLETED"

    # Direct unit test on compute_modified_z_score with 0 MAD and 0 median
    mod_z = compute_modified_z_score(x=10.0, median_val=0.0, mad_val=0.0)
    assert not np.isnan(mod_z)
    assert not np.isinf(mod_z)
    assert mod_z == 0.6745 * 10.0 / 1.0  # safe_mad floored at 1.0


def test_unexpected_silence_detects_suspected_stockout():
    """
    Assert that an abnormally long inter-arrival gap flags STOCKOUT_SUSPECTED.
    """
    # SKU typically sells every 2-3 days for 60 days, then goes silent for 20 days
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(80)]
    quantities = []
    for i in range(60):
        quantities.append(25.0 if i % 3 == 0 else 0.0)
    for i in range(20):  # 20 consecutive days of zero demand at end
        quantities.append(0.0)

    res = detect_anomalies_for_series(
        product_id="STOCKOUT-TEST-SKU",
        city_name="Delhi",
        dates=dates,
        quantities=quantities
    )

    stockout_alerts = [a for a in res["anomalies"] if a["anomaly_type"] == "STOCKOUT_SUSPECTED"]
    assert len(stockout_alerts) >= 1
    assert stockout_alerts[0]["detection_method"] == "INTERARRIVAL_GAP_SILENCE"
    assert stockout_alerts[0]["confidence"] == "HIGH"
    assert "Unexpected silence" in stockout_alerts[0]["description"]


def test_insufficient_history_guard():
    """
    Assert that SKUs with fewer than 30 observations are labeled INSUFFICIENT_HISTORY
    and alerts are suppressed.
    """
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(15)]
    quantities = [100.0 if i == 14 else 10.0 for i in range(15)]  # Potential spike on day 15

    res = detect_anomalies_for_series(
        product_id="NEW-SKU",
        city_name="Delhi",
        dates=dates,
        quantities=quantities,
        min_observations=30
    )

    assert res["status"] == "INSUFFICIENT_HISTORY"
    assert res["confidence"] == "INSUFFICIENT_HISTORY"
    assert len(res["anomalies"]) == 0
    assert "Insufficient history" in res["message"]
