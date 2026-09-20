import os
import io
import csv
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.main import app
from backend.db.session import Base, get_db
from backend.core.config import settings
import backend.api.upload as upload_module
from backend.models.product import Product
from backend.models.demand import DailyProductDemand
from backend.models.sales import SalesTransaction
from backend.models.upload import UploadJob
from backend.models.dataset import Dataset, SkuMapping
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_sku_res.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    bypass_scoping_check.set(True)
    orig_setting = settings.AUTO_CREATE_UNKNOWN_SKUS
    settings.AUTO_CREATE_UNKNOWN_SKUS = False
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

    db = TestingSessionLocal()
    ds = Dataset(name="Resolution Dataset", source="seed", is_active=True)
    db.add(ds)
    db.commit()

    known_prod = Product(
        product_id="KNOWN-SKU-1",
        product_name="Known Existing Product",
        is_active=True,
    )
    db.add(known_prod)
    db.commit()
    db.close()

    yield

    settings.AUTO_CREATE_UNKNOWN_SKUS = orig_setting
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


def test_unmapped_sku_failed_rows_and_resolution():
    client = TestClient(app)

    # 1. Upload CSV containing 1 known SKU and 1 unmapped SKU
    csv_content = (
        "date,product_id,city_name,order_id,cart_id,dim_customer_key,procured_quantity,unit_selling_price,total_discount_amount,total_weighted_landing_price\n"
        "2026-04-01,KNOWN-SKU-1,Bengaluru,ORD-101,CART-1,1001,15,45.0,0.0,35.0\n"
        "2026-04-01,UNMAPPED-SKU-99,Bengaluru,ORD-102,CART-2,1002,25,60.0,0.0,40.0\n"
    )

    resp = client.post(
        "/api/upload/sales",
        files={"file": ("test_sales.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )

    # Partial or rejection status code
    assert resp.status_code in [200, 202, 422]
    data = resp.json()
    upload_id = data["upload_id"]
    assert data["status"] in ["PARTIAL", "REJECTED"]
    assert "unmapped_skus" in data
    assert any(
        (item if isinstance(item, str) else item.get("sku")) == "UNMAPPED-SKU-99"
        for item in data["unmapped_skus"]
    )

    # 2. Test downloading failed rows CSV
    failed_rows_resp = client.get(f"/api/upload/{upload_id}/failed-rows")
    assert failed_rows_resp.status_code == 200
    assert "text/csv" in failed_rows_resp.headers["content-type"]
    failed_text = failed_rows_resp.text
    assert "error_reason" in failed_text
    assert "UNMAPPED-SKU-99" in failed_text

    # 3. Test SKU Resolution Endpoint: create as new product
    resolve_resp = client.post(
        f"/api/upload/{upload_id}/resolve-skus",
        json={
            "mappings": [
                {
                    "raw_sku": "UNMAPPED-SKU-99",
                    "resolved_product_id": "UNMAPPED-SKU-99",
                    "create_new": True,
                }
            ]
        },
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["status"] == "success"
    assert res_data["re_ingested_rows"] == 1

    # Verify product was auto-provisioned
    db = TestingSessionLocal()
    new_prod = db.query(Product).filter(Product.product_id == "UNMAPPED-SKU-99").first()
    assert new_prod is not None
    assert new_prod.is_provisional is True

    # Verify SKU mapping was saved
    mapping = db.query(SkuMapping).filter(SkuMapping.external_sku == "UNMAPPED-SKU-99").first()
    assert mapping is not None
    assert mapping.internal_product_id == "UNMAPPED-SKU-99"
    db.close()
