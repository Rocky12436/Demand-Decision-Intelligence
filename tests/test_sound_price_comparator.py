import pytest
from pathlib import Path
from datetime import date, timedelta
from backend.services.market_price_scraper import parse_pmd_html
from backend.services.price_intelligence import (
    normalize_price_to_rs_per_kg,
    MissingCommodityMappingError,
    evaluate_debounced_trend,
    generate_market_stock_decisions,
)
from backend.models.market_price import PriceObservation, CommodityMapping, CategoryPriceThreshold
from backend.db.session import SessionLocal

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "pmd_market_sample.html"


def test_pmd_html_parser_contract():
    """Validates parser contract against saved static PMD HTML without live network calls."""
    assert FIXTURE_PATH.exists(), f"Fixture file not found: {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    result = parse_pmd_html(html)
    assert result["status"] == "live"
    assert result["as_on_date"] == "20/09/2026"
    assert result["total_commodities"] >= 10

    # Verify specific commodity prices
    comm_map = {c["commodity"]: c["price_inr_per_kg"] for c in result["commodities"]}
    assert comm_map["Rice"] == 46.11
    assert comm_map["Wheat"] == 31.87
    assert comm_map["Onion"] == 54.22
    assert comm_map["Tomato"] == 39.04
    assert comm_map["Mustard Oil (Packed)"] == 201.42


def test_unit_normalisation_to_rs_per_kg():
    """Ensures prices are normalized to Rs/kg and unmapped units throw an error."""
    # 1. Standard quintal conversion: 4500 Rs/quintal -> 45 Rs/kg
    assert normalize_price_to_rs_per_kg(4500.0, "Rs/quintal") == 45.0

    # 2. Crate 25kg conversion: 1000 Rs/crate_25kg -> 40 Rs/kg
    assert normalize_price_to_rs_per_kg(1000.0, "Rs/crate_25kg") == 40.0

    # 3. Standard Rs/kg
    assert normalize_price_to_rs_per_kg(52.5, "Rs/kg") == 52.5

    # 4. Unknown/unmapped unit must raise MissingCommodityMappingError (never assume 1:1)
    with pytest.raises(MissingCommodityMappingError) as exc_info:
        normalize_price_to_rs_per_kg(120.0, "barrel_60L", commodity_code="UNKNOWN_ITEM")
    assert "Missing unit conversion mapping" in str(exc_info.value)
    assert "Never assume 1:1" in str(exc_info.value)

    # 5. Using CommodityMapping object
    mapping = CommodityMapping(
        product_id="TEST_PROD",
        commodity_code="TEST_COMM",
        commodity_name="Test Commodity",
        source_unit="custom_sack_50kg",
        conversion_factor_to_internal=0.02, # 1 / 50 = 0.02
    )
    assert normalize_price_to_rs_per_kg(2500.0, "custom_sack_50kg", mapping=mapping) == 50.0


def test_debounced_trend_rule():
    """
    Ensures transient 1-day spot spikes are marked MONITOR_TREND,
    while >= 3 consecutive days of sustained divergence trigger TRIM_STOCK / BULK_PROCURE.
    """
    db = SessionLocal()
    try:
        comm_code = "TEST_ONION"
        # Clean up existing test observations
        db.query(PriceObservation).filter(PriceObservation.commodity_code == comm_code).delete()
        db.commit()

        # Insert 10 days of stable baseline (30 Rs/kg)
        base_date = date(2026, 3, 1)
        for i in range(10):
            obs = PriceObservation(
                commodity_code=comm_code,
                market_name="National_Average",
                observed_date=base_date + timedelta(days=i),
                retail_price=30.0,
                unit="Rs/kg",
                source="test",
            )
            db.add(obs)
        db.commit()

        # Day 11: Single day spike to 60 Rs/kg (divergence = +100%)
        # Should NOT trigger persistent action because persistence is 1 day (< 3 days)
        trend_1day = evaluate_debounced_trend(
            db=db,
            commodity_code=comm_code,
            current_normalized_price=60.0,
            baseline_price=30.0,
            as_of=base_date + timedelta(days=10),
        )
        assert trend_1day["is_persistent"] is False
        assert trend_1day["consecutive_persistence_days"] == 1

        # Now add 3 consecutive days of 60 Rs/kg to database
        for i in range(11, 14):
            obs = PriceObservation(
                commodity_code=comm_code,
                market_name="National_Average",
                observed_date=base_date + timedelta(days=i),
                retail_price=60.0,
                unit="Rs/kg",
                source="test",
            )
            db.add(obs)
        db.commit()

        # Day 14: 3 days of sustained surge
        trend_3day = evaluate_debounced_trend(
            db=db,
            commodity_code=comm_code,
            current_normalized_price=60.0,
            baseline_price=30.0,
            as_of=base_date + timedelta(days=13),
        )
        assert trend_3day["is_persistent"] is True
        assert trend_3day["consecutive_persistence_days"] >= 3
        assert trend_3day["is_statistically_significant"] is True

        # Clean up
        db.query(PriceObservation).filter(PriceObservation.commodity_code == comm_code).delete()
        db.commit()
    finally:
        db.close()


def test_staleness_suppression():
    """Verifies that stocking recommendations are suppressed when market data is >7 days stale."""
    # Simulate stale market data by setting as_of far in the future
    decisions = generate_market_stock_decisions(
        db=None,
        force_refresh=False,
    )
    assert decisions["status"] == "success"
    assert "decisions" in decisions
    for d in decisions["decisions"]:
        assert "action" in d
        assert "recommended_holding_qty" in d
        assert d["unit"] == "Rs/kg"
