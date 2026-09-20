import os
import json
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
import backend.api.upload as upload_module
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.forecast import ForecastRun, ForecastItem
from backend.models.dataset import Dataset
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_freshness.db"
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
    upload_module.SessionLocal = TestingSessionLocal

    # Seed test dataset and initial demand
    db = TestingSessionLocal()
    ds = Dataset(name="Test Freshness Dataset", source="seed", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)

    prod = Product(
        product_id="TEST-FRESH-1",
        product_name="Freshness Test Item",
        is_active=True,
    )
    db.add(prod)
    db.commit()

    for i in range(1, 15):
        d = DailyProductDemand(
            dataset_id=ds.id,
            product_id="TEST-FRESH-1",
            city_name="Delhi",
            date_=date(2026, 4, i),
            total_quantity=20.0,
            avg_unit_price=50.0,
        )
        db.add(d)
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


def test_forecast_returns_freshness_metadata():
    client = TestClient(app)
    resp = client.get("/api/forecast?product_id=TEST-FRESH-1&horizon_days=7")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert "freshness" in data
    freshness = data["freshness"]
    assert "computed_at" in freshness
    assert "data_through" in freshness
    assert freshness["is_stale"] is False
    assert "model_name" in freshness
    assert freshness["data_through"] == "2026-04-14"


def test_staleness_detection_and_dynamic_recomputation():
    db = TestingSessionLocal()
    # Mark existing forecast runs as stale
    run = db.query(ForecastRun).first()
    assert run is not None
    run.is_stale = True
    db.commit()
    db.close()

    client = TestClient(app)
    # Reading the forecast should detect staleness and automatically recompute dynamically
    resp = client.get("/api/forecast?product_id=TEST-FRESH-1&horizon_days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["freshness"]["is_stale"] is False


def test_recompute_endpoint():
    db = TestingSessionLocal()
    ds = db.query(Dataset).first()
    db.close()

    client = TestClient(app)
    resp = client.post(
        "/api/forecast/recompute",
        json={"dataset_id": ds.id, "product_ids": ["TEST-FRESH-1"], "horizon_days": 14},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["recomputed_count"] == 1
    assert data["freshness"]["is_stale"] is False


def test_inventory_recommendations_includes_freshness():
    client = TestClient(app)
    resp = client.get("/api/inventory/recommendations?product_id=TEST-FRESH-1")
    assert resp.status_code == 200
    data = resp.json()
    assert "freshness" in data
    assert data["freshness"]["is_stale"] is False
    assert data["freshness"]["model_name"] == "EOQ_SafetyStock_95"
