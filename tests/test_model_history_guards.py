import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.session import SessionLocal
from backend.models.dataset import Dataset
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.services.forecast_service import select_model, compute_or_get_forecast

client = TestClient(app)

def test_select_model_fallbacks():
    # 1. 200 observations: Prophet satisfies requirements
    obs_200 = [10.0 + i % 5 for i in range(200)]
    model, reason, tier = select_model(obs_200, "Prophet_Weekly")
    assert model == "Prophet_Weekly"
    assert reason is None
    assert tier == "HIGH"

    # 2. 50 observations: Prophet requested, must fallback because < 120
    obs_50 = [10.0 + i % 5 for i in range(50)]
    model, reason, tier = select_model(obs_50, "Prophet_Weekly")
    assert model == "MovingAverage_30D"
    assert "Prophet requires >= 120 observations" in reason
    assert tier == "LOW"

    # 3. 75 observations: Ridge requested, satisfies >= 60
    obs_75 = [10.0 + i % 5 for i in range(75)]
    model, reason, tier = select_model(obs_75, "Ridge_LagFeatures")
    assert model == "Ridge_LagFeatures"
    assert reason is None
    assert tier == "MEDIUM"

    # 4. Intermittent series: 15 non-zero entries in 60 days
    intermittent = [10.0 if i % 4 == 0 else 0.0 for i in range(60)]
    model, reason, tier = select_model(intermittent, "Croston_SBA")
    assert model == "Croston_SBA"
    assert reason is None
    assert tier == "MEDIUM"

    # 5. Very sparse history: 5 observations falls back to naive
    obs_5 = [5.0, 6.0, 4.0, 5.0, 5.0]
    model, reason, tier = select_model(obs_5, "Prophet_Weekly")
    assert model == "Naive"
    assert tier == "LOW"


def test_forecast_confidence_tier_interval_widening():
    db = SessionLocal()
    try:
        # Create a test dataset
        dataset = Dataset(
            name="History Guard Test Dataset",
            source="upload",
            is_active=True,
            row_count=20,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        prod = db.query(Product).filter(Product.product_id == "SKU_GUARD_TEST").first()
        if not prod:
            prod = Product(
                product_id="SKU_GUARD_TEST",
                product_name="Guard SKU",
                is_active=True,
            )
            db.add(prod)
            db.commit()

        # Populate 20 days of demand (insufficient for Prophet, so fallback triggers)
        base_date = date(2026, 1, 1)
        for d in range(20):
            curr_date = base_date + timedelta(days=d)
            demand = DailyProductDemand(
                dataset_id=dataset.id,
                product_id="SKU_GUARD_TEST",
                city_name="Bengaluru",
                date_=curr_date,
                total_quantity=100.0,
                total_sales_value=1000.0,
                order_count=1,
            )
            db.add(demand)
        db.commit()

        # Compute forecast requesting Prophet_Weekly
        res = compute_or_get_forecast(
            db=db,
            dataset_id=dataset.id,
            product_id="SKU_GUARD_TEST",
            city_name="Bengaluru",
            horizon_days=7,
            model_name="Prophet_Weekly"
        )

        assert res["status"] == "success"
        # Should have downgraded from Prophet_Weekly because 20 < 120
        assert res["model_name"] != "Prophet_Weekly"
        assert res["requested_model"] == "Prophet_Weekly"
        assert res["confidence_tier"] == "LOW"
        assert res["model_fallback_reason"] is not None
        assert "requires >= 120 observations" in res["model_fallback_reason"]

        # Ensure uncertainty bands are present and reflect ±30% for LOW tier
        forecast_pts = res["forecast"]
        assert len(forecast_pts) == 7
        for pt in forecast_pts:
            assert pt["yhat_lower"] is not None
            assert pt["yhat_upper"] is not None
            assert pt["yhat_lower"] < pt["yhat"] < pt["yhat_upper"]
            # With mean 100.0 and 30% band, lower is 70 and upper is 130
            assert pt["yhat_lower"] == 70.0
            assert pt["yhat_upper"] == 130.0

        # Clean up
        db.query(DailyProductDemand).filter(DailyProductDemand.dataset_id == dataset.id).delete()
        db.query(Dataset).filter(Dataset.id == dataset.id).delete()
        db.commit()
    finally:
        db.close()


def test_forecast_api_returns_fallback_metadata():
    db = SessionLocal()
    try:
        dataset = Dataset(
            name="API Guard Test Dataset",
            source="upload",
            is_active=True,
            row_count=10,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        prod = db.query(Product).filter(Product.product_id == "SKU_API_GUARD").first()
        if not prod:
            prod = Product(
                product_id="SKU_API_GUARD",
                product_name="API Guard SKU",
                is_active=True,
            )
            db.add(prod)
            db.commit()

        base_date = date(2026, 2, 1)
        for d in range(10):
            curr_date = base_date + timedelta(days=d)
            demand = DailyProductDemand(
                dataset_id=dataset.id,
                product_id="SKU_API_GUARD",
                city_name="Bengaluru",
                date_=curr_date,
                total_quantity=50.0,
                total_sales_value=500.0,
                order_count=1,
            )
            db.add(demand)
        db.commit()

        # Call the API on this dataset requesting Prophet_Yearly
        resp = client.get(f"/api/forecast/?dataset_id={dataset.id}&product_id=SKU_API_GUARD&model_name=Prophet_Yearly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "model_name" in data
        assert "requested_model" in data
        assert data["requested_model"] == "Prophet_Yearly"
        assert "confidence_tier" in data
        assert data["confidence_tier"] == "LOW"
        assert "model_fallback_reason" in data
        assert "Prophet (Yearly Seasonality) requires >= 540 observations" in data["model_fallback_reason"]

        # Clean up
        db.query(DailyProductDemand).filter(DailyProductDemand.dataset_id == dataset.id).delete()
        db.query(Dataset).filter(Dataset.id == dataset.id).delete()
        db.commit()
    finally:
        db.close()
