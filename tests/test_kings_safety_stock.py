import os
import math
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.inventory import LeadTimeObservation
from backend.models.dataset import Dataset
from backend.services.dataset_service import bypass_scoping_check
from backend.services.inventory_service import (
    compute_safety_stock_kings,
    compute_safety_stock_classical,
    get_lead_time_stats,
)

TEST_DB_FILE = "./test_kings_ss.db"
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
    ds = Dataset(name="Kings Test Dataset", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id

    prod = Product(product_id="SKU-KING-1", product_name="King Safety Stock Product", is_active=True)
    db.add(prod)
    db.commit()

    # Seed 30 days of demand history
    base_date = date(2024, 1, 1)
    for i in range(30):
        d = base_date + timedelta(days=i)
        db.add(DailyProductDemand(
            dataset_id=ds_id,
            product_id="SKU-KING-1",
            city_name="Delhi",
            date_=d,
            total_quantity=100.0 + (10.0 if i % 2 == 0 else -10.0),
            total_sales_value=1000.0,
            order_count=10,
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


def test_kings_formula_reduces_exactly_to_classical_when_sigma_L_zero():
    """
    Unit test: with sigma_L = 0, King's formula reduces exactly to the classical formula:
    Z * sqrt(L * sigma_d^2 + d_bar^2 * 0) = Z * sigma_d * sqrt(L)
    """
    d_bar = 50.0
    sigma_d = 12.0
    L = 7.0
    z = 1.645

    ss_kings = compute_safety_stock_kings(
        avg_demand=d_bar,
        std_demand=sigma_d,
        lead_time_days=L,
        std_lead_time=0.0,  # sigma_L = 0
        z_score=z
    )

    # Classical theoretical without rounding
    classical_theoretical = round(z * sigma_d * math.sqrt(L), 2)
    assert ss_kings == classical_theoretical


def test_lead_time_variability_increases_safety_stock():
    """
    Assert that when lead time fluctuates (sigma_L > 0), King's safety stock
    exceeds classical constant lead-time safety stock.
    """
    d_bar = 50.0
    sigma_d = 12.0
    L = 7.0
    sigma_l = 3.0  # 3 days std dev in supplier deliveries
    z = 1.645

    ss_kings = compute_safety_stock_kings(d_bar, sigma_d, L, sigma_l, z)
    ss_classical = compute_safety_stock_classical(sigma_d, L, z)

    assert ss_kings > ss_classical
    # King's formula incorporates the d_bar^2 * sigma_L^2 term: (50^2 * 3^2) = 22500
    variance_combined = (L * (sigma_d ** 2)) + ((d_bar ** 2) * (sigma_l ** 2))
    expected = round(z * math.sqrt(variance_combined), 2)
    assert ss_kings == expected


def test_lead_time_observations_threshold_and_fallback():
    """
    Assert fallback to CV=0.25 when observations < 5, and calculation from sample
    when observations >= 5.
    """
    db = TestingSessionLocal()
    ds = db.query(Dataset).filter(Dataset.name == "Kings Test Dataset").first()
    ds_id = ds.id

    # 0 observations -> Fallback with CV=0.25
    stats_0 = get_lead_time_stats(db, ds_id, "SKU-KING-1")
    assert stats_0["confidence"] == "LOW"
    assert stats_0["is_fallback"] is True
    assert stats_0["lead_time_sd"] == round(0.25 * 7.0, 2)

    # Add 3 observations (< 5) -> Still LOW confidence fallback
    now = datetime.now(timezone.utc)
    for days in [6, 8, 7]:
        db.add(LeadTimeObservation(
            dataset_id=ds_id,
            product_id="SKU-KING-1",
            promised_days=7,
            actual_days=days,
            ordered_at=now - timedelta(days=days),
            received_at=now
        ))
    db.commit()

    stats_3 = get_lead_time_stats(db, ds_id, "SKU-KING-1")
    assert stats_3["confidence"] == "LOW"
    assert stats_3["observations_count"] == 3

    # Add 2 more observations (total 5 >= 5) -> HIGH confidence computed from sample
    for days in [9, 10]:
        db.add(LeadTimeObservation(
            dataset_id=ds_id,
            product_id="SKU-KING-1",
            promised_days=7,
            actual_days=days,
            ordered_at=now - timedelta(days=days),
            received_at=now
        ))
    db.commit()

    stats_5 = get_lead_time_stats(db, ds_id, "SKU-KING-1")
    assert stats_5["confidence"] == "HIGH"
    assert stats_5["is_fallback"] is False
    assert stats_5["observations_count"] == 5
    assert stats_5["lead_time_sd"] > 0
    db.close()


def test_api_exposes_both_formulas_and_delta():
    client = TestClient(app)
    db = TestingSessionLocal()
    ds = db.query(Dataset).filter(Dataset.name == "Kings Test Dataset").first()
    ds_id = ds.id
    db.close()

    # Default call (King's formula)
    resp = client.get(f"/api/inventory/recommendations?product_id=SKU-KING-1&dataset_id={ds_id}&city_name=Delhi")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"][0]

    assert "safety_stock_kings" in data
    assert "safety_stock_classical" in data
    assert "safety_stock_delta" in data
    assert data["formula_used"] == "kings"
    assert data["lead_time_confidence"] == "HIGH"
    assert data["safety_stock"] == data["safety_stock_kings"]

    # Call with use_classical=True
    resp_classic = client.get(f"/api/inventory/recommendations?product_id=SKU-KING-1&dataset_id={ds_id}&city_name=Delhi&use_classical=true")
    assert resp_classic.status_code == 200
    data_classic = resp_classic.json()["data"][0]
    assert data_classic["formula_used"] == "classical"
    assert data_classic["safety_stock"] == data_classic["safety_stock_classical"]
