import os
import io
import csv
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
from backend.core.config import settings
import backend.api.upload as upload_module
from backend.models.product import Product
from backend.models.dataset import Dataset
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_sku_prov.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_prov_db():
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


def test_hard_failure_on_unknown_skus_when_autoprovision_off():
    """
    Acceptance Criteria:
    - Uploading a CSV of entirely unknown SKUs returns 422, not 200.
    - The error_breakdown counts sum to error_rows exactly.
    """
    bypass_scoping_check.set(True)
    client = TestClient(app)

    # Disable auto-provisioning
    settings.AUTO_CREATE_UNKNOWN_SKUS = False

    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=list(upload_module.REQUIRED_COLUMNS))
    writer.writeheader()

    unknown_skus = ["UNKNOWN-A", "UNKNOWN-B", "UNKNOWN-C"]
    for i, sku in enumerate(unknown_skus):
        writer.writerow({
            "date_": f"2023-05-{10+i:02d}",
            "city_name": "Delhi",
            "order_id": f"ORD-ERR-{i}",
            "cart_id": f"CRT-ERR-{i}",
            "dim_customer_key": f"CUST-ERR-{i}",
            "procured_quantity": "50.0",
            "unit_selling_price": "20.0",
            "total_discount_amount": "0.0",
            "product_id": sku,
            "total_weighted_landing_price": "15.0",
        })

    files = {"file": ("unknown_skus.csv", io.BytesIO(csv_buf.getvalue().encode("utf-8")), "text/csv")}
    resp = client.post("/api/upload/sales", files=files)

    assert resp.status_code == 422, f"Expected 422 for unknown SKUs with auto-create off, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reason"] == "no_valid_rows"
    assert body["total_rows"] == 3

    # Error breakdown counts sum to error_rows exactly
    breakdown = body["error_breakdown"]
    total_breakdown_errors = sum(breakdown.values())
    assert total_breakdown_errors == 3, f"Breakdown sum {total_breakdown_errors} != error_rows 3"
    assert breakdown["unmapped_sku"] == 3
    assert set(body["unmapped_skus"]) == set(unknown_skus)


def test_success_and_provisional_product_when_autoprovision_on():
    """
    Acceptance Criteria:
    - With auto-provisioning on, the same CSV succeeds and creates provisional products.
    """
    bypass_scoping_check.set(True)
    db = TestingSessionLocal()
    client = TestClient(app)

    # Enable auto-provisioning
    settings.AUTO_CREATE_UNKNOWN_SKUS = True

    sku = "AUTO-PROV-SKU-777"
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=list(upload_module.REQUIRED_COLUMNS))
    writer.writeheader()
    writer.writerow({
        "date_": "2023-06-01",
        "city_name": "Delhi",
        "order_id": "ORD-PROV-1",
        "cart_id": "CRT-PROV-1",
        "dim_customer_key": "CUST-PROV-1",
        "procured_quantity": "30.0",
        "unit_selling_price": "40.0",
        "total_discount_amount": "0.0",
        "product_id": sku,
        "total_weighted_landing_price": "30.0",
    })

    files = {"file": ("prov_sku.csv", io.BytesIO(csv_buf.getvalue().encode("utf-8")), "text/csv")}
    resp = client.post("/api/upload/sales", files=files)
    assert resp.status_code == 200, f"Upload should succeed with auto-provisioning: {resp.text}"
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["valid_rows"] == 1

    # Verify provisional product created in DB
    prod = db.query(Product).filter(Product.product_id == sku).first()
    assert prod is not None, "Product should have been auto-provisioned"
    assert prod.is_provisional is True
    assert prod.l0_category == "Uncategorized"
    assert prod.product_name == sku
