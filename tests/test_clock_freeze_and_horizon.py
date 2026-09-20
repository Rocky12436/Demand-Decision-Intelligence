import os
from datetime import date, timedelta
import pytest
from freezegun import freeze_time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.dataset import Dataset
from backend.services.dataset_service import bypass_scoping_check
from backend.services.forecast_service import compute_or_get_forecast, GLOBAL_MODEL_REGISTRY

TEST_DB_FILE = "./test_clock_freeze.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    bypass_scoping_check.set(True)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    ds = Dataset(name="Clock Freeze Dataset", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id

    prod = Product(product_id="SKU-FREEZE-1", product_name="Clock Freeze Product", is_active=True)
    db.add(prod)
    db.commit()

    # Seed 30 days of demand history ending on 2024-03-31
    base_date = date(2024, 3, 2)
    for i in range(30):
        d = base_date + timedelta(days=i)
        record = DailyProductDemand(
            dataset_id=ds_id,
            product_id="SKU-FREEZE-1",
            city_name="ALL",
            date_=d,
            total_quantity=20.0 + (i % 5),
            total_sales_value=100.0,
            order_count=2,
            avg_unit_price=5.0
        )
        db.add(record)
    db.commit()
    db.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


def test_forecast_horizon_anchored_to_data_date_not_wall_clock():
    """
    Assert that forecast predictions and horizon dates are 100% identical
    whether the system clock is frozen in 2024 or in 2030.
    """
    client = TestClient(app)
    db = TestingSessionLocal()
    ds = db.query(Dataset).filter(Dataset.name == "Clock Freeze Dataset").first()
    ds_id = ds.id
    db.close()

    # 1. Run under frozen clock 2024-04-05 (5 days after data end 2024-03-31)
    with freeze_time("2024-04-05 12:00:00"):
        GLOBAL_MODEL_REGISTRY.clear()
        resp_2024 = client.get(f"/api/forecast?product_id=SKU-FREEZE-1&dataset_id={ds_id}&horizon_days=14")
        assert resp_2024.status_code == 200, resp_2024.text
        data_2024 = resp_2024.json()

    # 2. Run under frozen clock 2030-01-01 (almost 6 years in the future)
    with freeze_time("2030-01-01 12:00:00"):
        GLOBAL_MODEL_REGISTRY.clear()
        resp_2030 = client.get(f"/api/forecast?product_id=SKU-FREEZE-1&dataset_id={ds_id}&horizon_days=14")
        assert resp_2030.status_code == 200, resp_2030.text
        data_2030 = resp_2030.json()

    # Assert horizons start strictly on 2024-04-01 (as_of + 1 day)
    forecast_2024 = data_2024["forecast"]
    forecast_2030 = data_2030["forecast"]

    assert len(forecast_2024) == 14
    assert len(forecast_2030) == 14
    assert forecast_2024[0]["date"] == "2024-04-01"
    assert forecast_2030[0]["date"] == "2024-04-01"
    assert forecast_2024[-1]["date"] == "2024-04-14"
    assert forecast_2030[-1]["date"] == "2024-04-14"

    # Prediction arrays and values must be 100% IDENTICAL
    assert forecast_2024 == forecast_2030
    assert data_2024["predicted_mean"] == data_2030["predicted_mean"]


def test_historical_warning_triggered_when_over_90_days():
    """
    Assert that historical_warning object reflects whether as_of is >90 days behind
    the current calendar date.
    """
    client = TestClient(app)
    db = TestingSessionLocal()
    ds = db.query(Dataset).filter(Dataset.name == "Clock Freeze Dataset").first()
    ds_id = ds.id
    db.close()

    # Under 2024-04-05: 5 days behind 2024-03-31 -> is_historical is False
    with freeze_time("2024-04-05 12:00:00"):
        GLOBAL_MODEL_REGISTRY.clear()
        resp = client.get(f"/api/forecast?product_id=SKU-FREEZE-1&dataset_id={ds_id}&horizon_days=14")
        data = resp.json()
        hw = data["historical_warning"]
        assert hw["is_historical"] is False
        assert hw["days_behind"] == 5
        assert hw["message"] is None

    # Under 2025-01-01: ~276 days behind 2024-03-31 -> is_historical is True
    with freeze_time("2025-01-01 12:00:00"):
        GLOBAL_MODEL_REGISTRY.clear()
        resp = client.get(f"/api/forecast?product_id=SKU-FREEZE-1&dataset_id={ds_id}&horizon_days=14")
        data = resp.json()
        hw = data["historical_warning"]
        assert hw["is_historical"] is True
        assert hw["days_behind"] > 90
        assert "retrospectively from historical data" in hw["message"]
