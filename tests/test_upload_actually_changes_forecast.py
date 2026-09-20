import os
import io
import json
import csv
from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
import backend.api.upload as upload_module
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.sales import SalesTransaction
from backend.models.upload import UploadJob, ValidationResult
from backend.models.dataset import Dataset
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_throwaway.db"
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

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


def test_upload_actually_changes_forecast():
    bypass_scoping_check.set(True)
    db = TestingSessionLocal()
    client = TestClient(app)

    sku_str = "TEST-001"

    # Ensure baseline dataset exists
    demo_dataset = Dataset(
        id=1,
        name="Demo Data",
        source="seed",
        is_active=True,
        row_count=180
    )
    db.add(demo_dataset)
    db.commit()

    try:
        product = Product(
            product_id=sku_str,
            product_name="Test Product 001",
            is_active=True
        )
        db.add(product)
        db.commit()
    except Exception:
        db.rollback()

    # 1. Seed the DB with a known baseline dataset (180 days, flat demand of 10 units/day)
    start_date = date(2022, 1, 1)
    for i in range(180):
        cur_date = start_date + timedelta(days=i)
        demand_row = DailyProductDemand(
            id=i + 1,
            dataset_id=1,
            date_=cur_date,
            product_id=sku_str,
            city_name="Delhi",
            total_quantity=10.0,
            total_sales_value=100.0,
            total_discount_value=0.0,
            avg_unit_price=10.0,
            order_count=1
        )
        db.add(demand_row)
    db.commit()

    # 2. Call GET /api/forecast for TEST-001 and capture the predicted mean.
    forecast_resp = client.get("/api/forecast", params={"product_id": sku_str, "dataset_id": 1})
    assert forecast_resp.status_code == 200, f"Forecast initial call failed: {forecast_resp.text}"
    data = forecast_resp.json()
    predicted_mean_initial = data.get("predicted_mean") or data.get("yhat_mean")

    # 3. Upload a CSV via the real /api/upload/sales endpoint containing 60 days of demand at 100 units/day for the SAME SKU
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=list(upload_module.REQUIRED_COLUMNS))
    writer.writeheader()

    upload_start = date(2022, 7, 1)
    for i in range(60):
        d = upload_start + timedelta(days=i)
        writer.writerow({
            "date_": d.strftime("%Y-%m-%d"),
            "city_name": "Delhi",
            "order_id": f"ORD-TEST-{i:04d}",
            "cart_id": f"CART-{i:04d}",
            "dim_customer_key": f"CUST-{i:04d}",
            "procured_quantity": "100.0",
            "unit_selling_price": "10.0",
            "total_discount_amount": "0.0",
            "product_id": sku_str,
            "total_weighted_landing_price": "8.0",
        })

    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    files = {"file": ("test_sales.csv", io.BytesIO(csv_bytes), "text/csv")}
    form_data = {"dataset_id": "1"}

    upload_resp = client.post("/api/upload/sales", files=files, data=form_data)
    assert upload_resp.status_code == 200, f"Upload request failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    upload_id = upload_data.get("upload_id")

    job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    valid_rows = job.processed_rows if job else 0
    total_rows = job.total_rows if job else 0
    error_rows = total_rows - valid_rows

    assert valid_rows == 60, f"Expected 60 valid rows, got {valid_rows}"
    assert error_rows == 0, f"Expected 0 error rows, got {error_rows}"

    # 4. Call GET /api/forecast again and assert the predicted mean has increased by at least 2x
    forecast_resp_after = client.get("/api/forecast", params={"product_id": sku_str, "dataset_id": 1})
    assert forecast_resp_after.status_code == 200
    data_after = forecast_resp_after.json()
    predicted_mean_after = data_after.get("predicted_mean") or data_after.get("yhat_mean")

    assert predicted_mean_initial is not None
    assert predicted_mean_after is not None
    assert predicted_mean_after >= (predicted_mean_initial * 2.0), (
        f"Forecast did not update! Initial: {predicted_mean_initial}, After: {predicted_mean_after}"
    )
