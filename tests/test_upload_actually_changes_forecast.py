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

TEST_DB_FILE = "./test_throwaway.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    # Remove old throwaway db if exists
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

    # Create all tables in throwaway db
    Base.metadata.create_all(bind=test_engine)

    # Override get_db and SessionLocal in upload module
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
    db = TestingSessionLocal()
    client = TestClient(app)

    sku_str = "TEST-001"
    # Attempt numeric product_id if int-coerced, but prompt specifies SKU "TEST-001"
    # To test accurately, let's see how Product model handles it or seed both:
    try:
        product = Product(
            product_id=sku_str,
            product_name="Test Product 001",
            is_active=True
        )
        db.add(product)
        db.commit()
    except Exception as e:
        db.rollback()

    # 1. Seed the DB with a known baseline dataset (180 days, flat demand of 10 units/day)
    start_date = date(2022, 1, 1)
    for i in range(180):
        cur_date = start_date + timedelta(days=i)
        demand_row = DailyProductDemand(
            id=i + 1,
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
    # Note: Checking GET /api/forecast and /api/forecast/{product_id} and /api/forecast/results
    forecast_resp = client.get("/api/forecast", params={"product_id": sku_str})
    predicted_mean_initial = None
    if forecast_resp.status_code == 200:
        data = forecast_resp.json()
        predicted_mean_initial = data.get("predicted_mean") or data.get("yhat_mean")
    elif forecast_resp.status_code == 404:
        # Check alternative endpoint
        alt_resp = client.get(f"/api/forecast/{sku_str}")
        if alt_resp.status_code == 200:
            data = alt_resp.json()
            predicted_mean_initial = data.get("predicted_mean")

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

    upload_resp = client.post("/api/upload/sales", files=files)
    assert upload_resp.status_code == 200, f"Upload request failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    upload_id = upload_data.get("upload_id")

    # The background task executes synchronously when using TestClient or we query the DB
    job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    validation_results = db.query(ValidationResult).filter(ValidationResult.upload_id == upload_id).all()
    validation_summary = {vr.check_name: {"status": vr.status, "details": vr.details} for vr in validation_results}

    # 4. Assert upload_jobs.valid_rows == 60 and error_rows == 0
    valid_rows = job.processed_rows if job else 0
    total_rows = job.total_rows if job else 0
    error_rows = total_rows - valid_rows

    if valid_rows != 60 or error_rows != 0:
        print("\n" + "=" * 60)
        print("DIAGNOSTIC REPORT: SKU-MAPPING / UPLOAD VALIDATION FAILED")
        print(f"Total Rows: {total_rows}, Valid Rows: {valid_rows}, Error Rows: {error_rows}")
        print(f"Job Status: {job.status if job else 'None'}")
        print(f"Job Error Summary: {job.error_summary if job else 'None'}")
        print(f"Validation Checks: {json.dumps(validation_summary, indent=2)}")
        print("=" * 60 + "\n")

    assert valid_rows == 60, f"Expected 60 valid rows, got {valid_rows}. Validation info: {validation_summary}"
    assert error_rows == 0, f"Expected 0 error rows, got {error_rows}. Validation info: {validation_summary}"

    # 5. Call GET /api/forecast again and assert the predicted mean has increased by a materially large margin (at least 2x)
    forecast_resp_after = client.get("/api/forecast", params={"product_id": sku_str})
    predicted_mean_after = None
    if forecast_resp_after.status_code == 200:
        data_after = forecast_resp_after.json()
        predicted_mean_after = data_after.get("predicted_mean") or data_after.get("yhat_mean")

    assert predicted_mean_initial is not None, "GET /api/forecast initial call failed or returned no predicted mean."
    assert predicted_mean_after is not None, "GET /api/forecast second call failed or returned no predicted mean."
    assert predicted_mean_after >= (predicted_mean_initial * 2.0), (
        f"Forecast did not update! Initial: {predicted_mean_initial}, After: {predicted_mean_after}"
    )
