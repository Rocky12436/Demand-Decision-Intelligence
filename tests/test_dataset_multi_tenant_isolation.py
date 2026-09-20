import os
import io
import csv
from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
import backend.api.upload as upload_module
from backend.models.dataset import Dataset
from backend.models.user import User, Role
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_isolation.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_isolation_db():
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

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


def test_user_a_upload_zero_effect_on_user_b():
    """
    Acceptance Criteria: A test proves user A's upload has zero effect on user B's forecasts.
    """
    bypass_scoping_check.set(True)
    db = TestingSessionLocal()
    client = TestClient(app)

    # 1. Create Role & Users
    role = Role(id=1, name="viewer", description="Viewer")
    db.add(role)
    db.commit()

    user_a = User(id=101, email="user_a@tenant.com", username="user_a", hashed_password="pw", role_id=1)
    user_b = User(id=102, email="user_b@tenant.com", username="user_b", hashed_password="pw", role_id=1)
    db.add_all([user_a, user_b])
    db.commit()

    # 2. Create Scoped Datasets for User A and User B
    dataset_a = Dataset(id=10, user_id=101, name="Tenant A Dataset", source="upload", is_active=True)
    dataset_b = Dataset(id=20, user_id=102, name="Tenant B Dataset", source="upload", is_active=True)
    db.add_all([dataset_a, dataset_b])
    db.commit()

    shared_sku = "SHARED-SKU-999"

    # 3. User A uploads CSV with 200 units/day for SHARED-SKU-999
    csv_a = io.StringIO()
    writer_a = csv.DictWriter(csv_a, fieldnames=list(upload_module.REQUIRED_COLUMNS))
    writer_a.writeheader()
    for i in range(10):
        d = date(2023, 1, 1) + timedelta(days=i)
        writer_a.writerow({
            "date_": d.strftime("%Y-%m-%d"),
            "city_name": "Bengaluru",
            "order_id": f"ORD-A-{i}",
            "cart_id": f"CRT-A-{i}",
            "dim_customer_key": f"CUST-A-{i}",
            "procured_quantity": "200.0",
            "unit_selling_price": "50.0",
            "total_discount_amount": "0.0",
            "product_id": shared_sku,
            "total_weighted_landing_price": "40.0",
        })
    files_a = {"file": ("tenant_a.csv", io.BytesIO(csv_a.getvalue().encode("utf-8")), "text/csv")}
    resp_a = client.post("/api/upload/sales", files=files_a, data={"dataset_id": "10"})
    assert resp_a.status_code == 200, f"User A upload failed: {resp_a.text}"

    # 4. User B uploads CSV with 10 units/day for the EXACT SAME SHARED-SKU-999
    csv_b = io.StringIO()
    writer_b = csv.DictWriter(csv_b, fieldnames=list(upload_module.REQUIRED_COLUMNS))
    writer_b.writeheader()
    for i in range(10):
        d = date(2023, 1, 1) + timedelta(days=i)
        writer_b.writerow({
            "date_": d.strftime("%Y-%m-%d"),
            "city_name": "Bengaluru",
            "order_id": f"ORD-B-{i}",
            "cart_id": f"CRT-B-{i}",
            "dim_customer_key": f"CUST-B-{i}",
            "procured_quantity": "10.0",
            "unit_selling_price": "50.0",
            "total_discount_amount": "0.0",
            "product_id": shared_sku,
            "total_weighted_landing_price": "40.0",
        })
    files_b = {"file": ("tenant_b.csv", io.BytesIO(csv_b.getvalue().encode("utf-8")), "text/csv")}
    resp_b = client.post("/api/upload/sales", files=files_b, data={"dataset_id": "20"})
    assert resp_b.status_code == 200, f"User B upload failed: {resp_b.text}"

    # 5. Query Forecast for User A (dataset_id=10)
    forecast_a = client.get("/api/forecast", params={"product_id": shared_sku, "dataset_id": 10})
    assert forecast_a.status_code == 200
    mean_a = forecast_a.json()["predicted_mean"]

    # 6. Query Forecast for User B (dataset_id=20)
    forecast_b = client.get("/api/forecast", params={"product_id": shared_sku, "dataset_id": 20})
    assert forecast_b.status_code == 200
    mean_b = forecast_b.json()["predicted_mean"]

    # Verify Strict Multi-Tenant Isolation
    assert mean_a == 200.0, f"Expected User A forecast mean to be 200.0, got {mean_a}"
    assert mean_b == 10.0, f"Expected User B forecast mean to be 10.0, got {mean_b}"

    # 7. Query Inventory for User A vs User B
    inv_a = client.get("/api/inventory/recommendations", params={"product_id": shared_sku, "dataset_id": 10})
    assert inv_a.status_code == 200
    assert inv_a.json()["data"][0]["mean_daily_demand"] == 200.0

    inv_b = client.get("/api/inventory/recommendations", params={"product_id": shared_sku, "dataset_id": 20})
    assert inv_b.status_code == 200
    assert inv_b.json()["data"][0]["mean_daily_demand"] == 10.0
