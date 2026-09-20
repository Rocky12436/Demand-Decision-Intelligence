import os
import io
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
from backend.models.demand import DailyProductDemand
from backend.models.sales import SalesTransaction
from backend.models.upload import UploadJob
from backend.models.dataset import Dataset
from backend.models.forecast import ForecastRun
from backend.services.dataset_service import bypass_scoping_check

TEST_DB_FILE = "./test_idempotent.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    bypass_scoping_check.set(True)
    orig_setting = settings.AUTO_CREATE_UNKNOWN_SKUS
    settings.AUTO_CREATE_UNKNOWN_SKUS = True

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

    settings.AUTO_CREATE_UNKNOWN_SKUS = orig_setting
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


SAMPLE_CSV_CONTENT = """date,city_name,order_id,cart_id,dim_customer_key,procured_quantity,unit_selling_price,total_discount_amount,product_id,total_weighted_landing_price
2024-03-01,Delhi,ORD001,CART001,CUST001,10.0,100.0,0.0,SKU-IDEMP-1,80.0
2024-03-02,Delhi,ORD002,CART002,CUST002,15.0,100.0,0.0,SKU-IDEMP-1,80.0
"""


def test_duplicate_file_returns_409_without_allow_duplicate():
    client = TestClient(app)

    db = TestingSessionLocal()
    ds = Dataset(name="Idempotent Test Dataset 1", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id
    db.close()

    # 1. First upload -> should succeed
    file_bytes = SAMPLE_CSV_CONTENT.encode("utf-8")
    resp1 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=false",
        files={"file": ("sales_1.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["status"] == "COMPLETED"
    job1_id = data1["upload_id"]

    # 2. Second upload of exact same bytes without allow_duplicate -> 409 Conflict
    resp2 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=false",
        files={"file": ("sales_1_duplicate.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp2.status_code == 409
    data2 = resp2.json()
    assert data2["prior_job_id"] == job1_id


def test_allow_duplicate_replace_mode_does_not_double_demand():
    client = TestClient(app)

    db = TestingSessionLocal()
    ds = Dataset(name="Idempotent Test Dataset 2", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id
    db.close()

    file_bytes = SAMPLE_CSV_CONTENT.encode("utf-8")

    # Upload 1
    resp1 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=false",
        files={"file": ("sales_replace.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp1.status_code == 200

    # Upload 2 with allow_duplicate=true and conflict_mode=REPLACE
    resp2 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=true",
        files={"file": ("sales_replace.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp2.status_code == 200

    db = TestingSessionLocal()
    d1 = db.query(DailyProductDemand).filter(
        DailyProductDemand.dataset_id == ds_id,
        DailyProductDemand.product_id == "SKU-IDEMP-1",
        DailyProductDemand.date_ == date(2024, 3, 1)
    ).first()
    assert d1 is not None
    # In REPLACE mode, 10.0 is replaced by 10.0, NOT doubled to 20.0
    assert d1.total_quantity == 10.0
    db.close()


def test_accumulate_mode_sums_demand():
    client = TestClient(app)

    db = TestingSessionLocal()
    ds = Dataset(name="Idempotent Test Dataset 3", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id
    db.close()

    file_bytes = SAMPLE_CSV_CONTENT.encode("utf-8")

    # Upload 1
    resp1 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=false",
        files={"file": ("sales_acc.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp1.status_code == 200

    # Upload 2 with allow_duplicate=true and conflict_mode=ACCUMULATE
    resp2 = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=ACCUMULATE&allow_duplicate=true",
        files={"file": ("sales_acc.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp2.status_code == 200

    db = TestingSessionLocal()
    d1 = db.query(DailyProductDemand).filter(
        DailyProductDemand.dataset_id == ds_id,
        DailyProductDemand.product_id == "SKU-IDEMP-1",
        DailyProductDemand.date_ == date(2024, 3, 1)
    ).first()
    assert d1 is not None
    # In ACCUMULATE mode, 10.0 + 10.0 = 20.0
    assert d1.total_quantity == 20.0
    db.close()


def test_delete_upload_job_rollback():
    client = TestClient(app)

    db = TestingSessionLocal()
    ds = Dataset(name="Idempotent Test Dataset 4", source="upload", is_active=True)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    ds_id = ds.id

    # Create dummy forecast run to test staleness marking
    fr = ForecastRun(
        dataset_id=ds_id,
        model_name="Prophet_MovingAvg_Ensemble",
        horizon_days=14,
        status="COMPLETED",
        is_stale=False
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    fr_id = fr.id
    db.close()

    file_bytes = SAMPLE_CSV_CONTENT.encode("utf-8")
    resp = client.post(
        f"/api/upload/sales?dataset_id={ds_id}&conflict_mode=REPLACE&allow_duplicate=false",
        files={"file": ("sales_del.csv", io.BytesIO(file_bytes), "text/csv")}
    )
    assert resp.status_code == 200
    upload_id = resp.json()["upload_id"]

    # Verify rows exist
    db = TestingSessionLocal()
    tx_count = db.query(SalesTransaction).filter(SalesTransaction.upload_id == upload_id).count()
    assert tx_count == 2
    db.close()

    # Call DELETE /api/upload/{upload_id}
    del_resp = client.delete(f"/api/upload/{upload_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "success"
    assert del_data["deleted_sales_count"] == 2

    # Verify rows deleted and forecast marked stale
    db = TestingSessionLocal()
    tx_count_after = db.query(SalesTransaction).filter(SalesTransaction.upload_id == upload_id).count()
    assert tx_count_after == 0

    fr_after = db.query(ForecastRun).filter(ForecastRun.id == fr_id).first()
    assert fr_after.is_stale is True
    db.close()
