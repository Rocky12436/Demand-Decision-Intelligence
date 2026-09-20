import os
import json
from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.dataset import Dataset
from backend.models.forecast import ForecastRun
from backend.services.dataset_service import bypass_scoping_check
from backend.services.forecast_service import GLOBAL_MODEL_REGISTRY

TEST_DB_FILE = "./test_runtime_cache.db"
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
    ds = Dataset(name="Cache Test Dataset", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id

    prod = Product(product_id="SKU-CACHE-1", product_name="Cache Product", is_active=True)
    db.add(prod)
    db.commit()

    # Initial 10 days of demand ending on 2024-05-10
    start_d = date(2024, 5, 1)
    for i in range(10):
        d = start_d + timedelta(days=i)
        db.add(DailyProductDemand(
            dataset_id=ds_id,
            product_id="SKU-CACHE-1",
            city_name="ALL",
            date_=d,
            total_quantity=50.0,
            total_sales_value=500.0,
            order_count=5,
            avg_unit_price=10.0
        ))
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


def test_runtime_cache_hit_and_automatic_refit_on_data_append():
    GLOBAL_MODEL_REGISTRY.clear()
    client = TestClient(app)

    db = TestingSessionLocal()
    ds = db.query(Dataset).filter(Dataset.name == "Cache Test Dataset").first()
    ds_id = ds.id
    db.close()

    # 1. First call: Cache miss -> Fits runtime model
    resp1 = client.get(f"/api/forecast?product_id=SKU-CACHE-1&dataset_id={ds_id}&horizon_days=14")
    assert resp1.status_code == 200
    data1 = resp1.json()

    key_initial = GLOBAL_MODEL_REGISTRY.get_key(ds_id, "SKU-CACHE-1", date(2024, 5, 10), "Prophet_MovingAvg_Ensemble")
    assert GLOBAL_MODEL_REGISTRY.refit_counts[key_initial] == 1
    assert GLOBAL_MODEL_REGISTRY.total_fits == 1
    assert GLOBAL_MODEL_REGISTRY.total_hits == 0

    # Verify metrics persisted in DB
    db = TestingSessionLocal()
    run = db.query(ForecastRun).filter(ForecastRun.dataset_id == ds_id).order_by(ForecastRun.id.desc()).first()
    assert run is not None
    assert run.metrics_summary is not None
    metrics = json.loads(run.metrics_summary)
    assert "mae" in metrics
    assert "rmse" in metrics
    db.close()

    # 2. Second call with same data & as_of: Cache hit -> No new fit!
    resp2 = client.get(f"/api/forecast?product_id=SKU-CACHE-1&dataset_id={ds_id}&horizon_days=14")
    assert resp2.status_code == 200
    assert GLOBAL_MODEL_REGISTRY.refit_counts[key_initial] == 1
    assert GLOBAL_MODEL_REGISTRY.total_fits == 1
    assert GLOBAL_MODEL_REGISTRY.total_hits == 1

    # 3. Append new daily demand record for 2024-05-11
    db = TestingSessionLocal()
    db.add(DailyProductDemand(
        dataset_id=ds_id,
        product_id="SKU-CACHE-1",
        city_name="ALL",
        date_=date(2024, 5, 11),
        total_quantity=100.0,
        total_sales_value=1000.0,
        order_count=10,
        avg_unit_price=10.0
    ))
    db.commit()
    db.close()

    # 4. Third call: as_of has advanced to 2024-05-11 -> New cache key -> Automatic refit triggered!
    resp3 = client.get(f"/api/forecast?product_id=SKU-CACHE-1&dataset_id={ds_id}&horizon_days=14")
    assert resp3.status_code == 200
    data3 = resp3.json()

    key_updated = GLOBAL_MODEL_REGISTRY.get_key(ds_id, "SKU-CACHE-1", date(2024, 5, 11), "Prophet_MovingAvg_Ensemble")
    assert key_updated != key_initial
    assert GLOBAL_MODEL_REGISTRY.refit_counts[key_updated] == 1
    assert GLOBAL_MODEL_REGISTRY.total_fits == 2
    # Forecast mean changed because new 100.0 quantity point was ingested
    assert data3["predicted_mean"] > data1["predicted_mean"]
