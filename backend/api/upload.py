import csv
import json
from datetime import datetime
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session

from backend.db.session import get_db, SessionLocal
from backend.models.product import Product
from backend.models.sales import SalesTransaction
from backend.models.upload import UploadJob, ValidationResult
from backend.models.demand import DailyProductDemand


router = APIRouter()


@router.get("/test")
def upload_test():
    return {
        "message": "Upload API is working"
    }


REQUIRED_COLUMNS = {
    "date_",
    "city_name",
    "order_id",
    "cart_id",
    "dim_customer_key",
    "procured_quantity",
    "unit_selling_price",
    "total_discount_amount",
    "product_id",
    "total_weighted_landing_price",
}

IGNORED_COLUMNS = {
    "Unnamed: 0",
    "Unnamed: 0.1",
}


def parse_date(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(value):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def get_file_size(file: UploadFile):
    try:
        current_position = file.file.tell()
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(current_position)
        return size
    except Exception:
        return None


def process_sales_upload_background(upload_id: int, text: str):
    """Background Task: Processes uploaded sales CSV, auto-provisions missing products,
    populates SalesTransaction & DailyProductDemand, and triggers Price Elasticity Retraining."""
    db = SessionLocal()
    upload_job = None
    try:
        upload_job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
        if not upload_job:
            return

        upload_job.status = "PROCESSING"
        db.commit()

        reader = csv.DictReader(text.splitlines())
        product_ids = {str(pid) for (pid,) in db.query(Product.product_id).all()}

        total_rows = 0
        valid_rows = 0

        missing_dates = invalid_dates = 0
        missing_product_ids = invalid_product_ids = unmatched_product_ids = 0
        missing_quantity = invalid_quantity = negative_quantity = 0
        missing_price = invalid_price = negative_price = 0
        duplicate_rows = 0

        seen_rows = set()
        batch = []
        BATCH_SIZE = 1000

        agg_map = {}

        for row in reader:
            total_rows += 1
            for column in IGNORED_COLUMNS:
                row.pop(column, None)

            errors = []
            date_value = (row.get("date_") or "").strip()
            parsed_date = parse_date(date_value) if date_value else None
            if not date_value:
                missing_dates += 1
                errors.append("missing_date")
            elif parsed_date is None:
                invalid_dates += 1
                errors.append("invalid_date")

            product_value = (row.get("product_id") or "").strip()
            if not product_value:
                missing_product_ids += 1
                errors.append("missing_product_id")
                product_id = None
            else:
                product_id = product_value
                # Auto-provision new product if it does not exist in the products table
                if product_id not in product_ids:
                    new_product = Product(
                        product_id=product_id,
                        product_name=f"Product {product_id}",
                        l0_category="General",
                        is_active=True
                    )
                    db.add(new_product)
                    db.flush()
                    product_ids.add(product_id)

            quantity_value = (row.get("procured_quantity") or "").strip()
            quantity = parse_float(quantity_value) if quantity_value else None
            if not quantity_value:
                missing_quantity += 1
                errors.append("missing_quantity")
            elif quantity is None:
                invalid_quantity += 1
                errors.append("invalid_quantity")
            elif quantity < 0:
                negative_quantity += 1
                errors.append("negative_quantity")

            price_value = (row.get("unit_selling_price") or "").strip()
            price = parse_float(price_value) if price_value else None
            if not price_value:
                missing_price += 1
                errors.append("missing_price")
            elif price is None:
                invalid_price += 1
                errors.append("invalid_price")
            elif price < 0:
                negative_price += 1
                errors.append("negative_price")

            discount_value = (row.get("total_discount_amount") or "").strip()
            discount = parse_float(discount_value) if discount_value else 0.0
            if discount is None:
                discount = 0.0

            duplicate_key = tuple(row.get(column) for column in sorted(REQUIRED_COLUMNS if REQUIRED_COLUMNS.issubset(row.keys()) else row.keys()))
            if duplicate_key in seen_rows:
                duplicate_rows += 1
                errors.append("duplicate_row")
            else:
                seen_rows.add(duplicate_key)

            if not errors and parsed_date and product_id is not None and quantity is not None and price is not None:
                city = row.get("city_name", "ALL")
                transaction = SalesTransaction(
                    upload_id=upload_job.id,
                    date_=parsed_date,
                    city_name=city,
                    order_id=row.get("order_id"),
                    cart_id=row.get("cart_id"),
                    dim_customer_key=row.get("dim_customer_key"),
                    procured_quantity=quantity,
                    unit_selling_price=price,
                    total_discount_amount=discount,
                    product_id=product_id,
                    total_weighted_landing_price=parse_float(row.get("total_weighted_landing_price")),
                )
                batch.append(transaction)
                valid_rows += 1

                # Dynamic Daily Aggregation accumulator
                agg_key = (parsed_date, product_id, city)
                if agg_key not in agg_map:
                    agg_map[agg_key] = {"quantity": 0.0, "revenue": 0.0, "discount": 0.0, "orders": set()}
                agg_map[agg_key]["quantity"] += quantity
                agg_map[agg_key]["revenue"] += (quantity * price)
                agg_map[agg_key]["discount"] += discount
                if row.get("order_id"):
                    agg_map[agg_key]["orders"].add(row.get("order_id"))

            if len(batch) >= BATCH_SIZE:
                db.add_all(batch)
                db.flush()
                batch.clear()

        if batch:
            db.add_all(batch)
            db.flush()
            batch.clear()

        # Update Validation Result records in DB
        validation_checks = [
            ("required_columns", "PASS", "All required columns are present."),
            ("date_validation", "PASS" if missing_dates == 0 and invalid_dates == 0 else "FAIL", f"Missing: {missing_dates}; Invalid: {invalid_dates}"),
            ("product_id_validation", "PASS" if missing_product_ids == 0 and invalid_product_ids == 0 else "WARNING", f"Missing: {missing_product_ids}; Invalid: {invalid_product_ids}; Unmatched: {unmatched_product_ids}"),
            ("quantity_validation", "PASS" if missing_quantity == 0 and invalid_quantity == 0 and negative_quantity == 0 else "FAIL", f"Missing: {missing_quantity}; Invalid: {invalid_quantity}; Negative: {negative_quantity}"),
            ("price_validation", "PASS" if missing_price == 0 and invalid_price == 0 and negative_price == 0 else "FAIL", f"Missing: {missing_price}; Invalid: {invalid_price}; Negative: {negative_price}"),
            ("duplicate_validation", "PASS" if duplicate_rows == 0 else "WARNING", f"Duplicate rows: {duplicate_rows}"),
        ]

        for check_name, check_status, details in validation_checks:
            db.add(ValidationResult(upload_id=upload_job.id, check_name=check_name, status=check_status, details=details))

        # Dynamic Upsert into DailyProductDemand
        for (d_date, p_id, city), metrics in agg_map.items():
            existing = db.query(DailyProductDemand).filter(
                DailyProductDemand.date_ == d_date,
                DailyProductDemand.product_id == p_id,
                DailyProductDemand.city_name == city
            ).first()
            if existing:
                existing.total_quantity = metrics["quantity"]
                existing.total_sales_value = metrics["revenue"]
                existing.total_discount_value = metrics["discount"]
                existing.order_count = len(metrics["orders"])
                if existing.total_quantity > 0:
                    existing.avg_unit_price = round(existing.total_sales_value / existing.total_quantity, 2)
            else:
                unit_p = round(metrics["revenue"] / metrics["quantity"], 2) if metrics["quantity"] > 0 else 0.0
                new_demand = DailyProductDemand(
                    date_=d_date,
                    product_id=p_id,
                    city_name=city,
                    total_quantity=metrics["quantity"],
                    total_sales_value=metrics["revenue"],
                    total_discount_value=metrics["discount"],
                    avg_unit_price=unit_p,
                    order_count=len(metrics["orders"])
                )
                db.add(new_demand)

        upload_job.total_rows = total_rows
        upload_job.processed_rows = valid_rows
        upload_job.status = "COMPLETED" if valid_rows > 0 else "FAILED"
        if valid_rows == 0:
            upload_job.error_summary = "No valid sales rows were found."
        upload_job.completed_at = datetime.utcnow()
        db.commit()

        # Auto-trigger Price Elasticity Retraining Engine
        try:
            from analytics.price_elasticity_engine import PriceElasticityEngine
            PriceElasticityEngine().run_analysis()
        except Exception as pe_err:
            print(f"Background elasticity auto-retrain trigger: {pe_err}")

    except Exception as exc:
        db.rollback()
        if upload_job:
            upload_job.status = "FAILED"
            upload_job.error_summary = f"Background processing failure: {str(exc)}"
            db.commit()
    finally:
        db.close()


@router.post("/sales")
def upload_sales(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    file_size = get_file_size(file)

    upload_job = UploadJob(
        filename=file.filename,
        file_type="sales",
        file_size_bytes=file_size,
        status="PENDING",
        total_rows=0,
        processed_rows=0,
    )
    db.add(upload_job)
    db.commit()
    db.refresh(upload_job)

    try:
        file.file.seek(0)
        content = file.file.read()
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        upload_job.status = "FAILED"
        upload_job.error_summary = "CSV must use UTF-8 encoding."
        db.commit()
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding.")

    reader = csv.DictReader(text.splitlines())
    actual_columns = set(reader.fieldnames or [])
    missing_columns = REQUIRED_COLUMNS - actual_columns

    if missing_columns:
        validation = ValidationResult(
            upload_id=upload_job.id,
            check_name="required_columns",
            status="FAIL",
            details=json.dumps({"missing_columns": sorted(missing_columns)}),
        )
        db.add(validation)
        upload_job.status = "FAILED"
        upload_job.error_summary = f"Missing required columns: {sorted(missing_columns)}"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={"message": "Missing required columns.", "missing_columns": sorted(missing_columns)},
        )

    # Queue background task for validation, ingestion, demand aggregation, and elasticity retraining
    background_tasks.add_task(process_sales_upload_background, upload_job.id, text)

    return {
        "upload_id": upload_job.id,
        "filename": upload_job.filename,
        "status": upload_job.status,
        "message": "File uploaded successfully. Processing and model retraining triggered in background.",
        "created_at": upload_job.created_at,
    }


@router.get("/uploads")
def get_uploads(
    db: Session = Depends(get_db),
):
    uploads = db.query(UploadJob).order_by(UploadJob.created_at.desc()).all()
    return {
        "total": len(uploads),
        "uploads": [
            {
                "id": upload.id,
                "filename": upload.filename,
                "file_type": upload.file_type,
                "file_size_bytes": upload.file_size_bytes,
                "status": upload.status,
                "total_rows": upload.total_rows,
                "processed_rows": upload.processed_rows,
                "error_summary": upload.error_summary,
                "created_at": upload.created_at,
                "completed_at": upload.completed_at,
            }
            for upload in uploads
        ],
    }


@router.get("/uploads/{upload_id}")
def get_upload(
    upload_id: int,
    db: Session = Depends(get_db),
):
    upload = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")

    return {
        "id": upload.id,
        "filename": upload.filename,
        "file_type": upload.file_type,
        "file_size_bytes": upload.file_size_bytes,
        "status": upload.status,
        "total_rows": upload.total_rows,
        "processed_rows": upload.processed_rows,
        "error_summary": upload.error_summary,
        "created_at": upload.created_at,
        "completed_at": upload.completed_at,
    }


@router.get("/validation/{upload_id}")
def get_validation_results(
    upload_id: int,
    db: Session = Depends(get_db),
):
    upload = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found.")

    results = db.query(ValidationResult).filter(ValidationResult.upload_id == upload_id).order_by(ValidationResult.id).all()

    return {
        "upload_id": upload_id,
        "filename": upload.filename,
        "status": upload.status,
        "validation_results": [
            {
                "id": result.id,
                "check_name": result.check_name,
                "status": result.status,
                "details": result.details,
                "created_at": result.created_at,
            }
            for result in results
        ],
    }