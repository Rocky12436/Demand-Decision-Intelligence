import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
import rapidfuzz

from backend.core.config import settings
from backend.db.session import get_db, SessionLocal
from backend.models.product import Product
from backend.models.sales import SalesTransaction
from backend.models.upload import UploadJob, ValidationResult
from backend.models.demand import DailyProductDemand
from backend.models.dataset import Dataset, SkuMapping
from backend.models.forecast import ForecastRun, ForecastItem
from backend.models.inventory import InventoryRecommendation
from backend.models.anomaly import AnomalyAlert
from backend.services.dataset_service import resolve_dataset
from backend.services.duckdb_service import sync_dataset_to_duckdb

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FAILED_ROWS_DIR = PROJECT_ROOT / "dataset" / "failed_rows"
FAILED_ROWS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory store for fast access to failed rows per upload job
FAILED_ROWS_CACHE: Dict[int, List[Dict[str, Any]]] = {}


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


def save_failed_rows(upload_id: int, failed_rows: List[Dict[str, Any]]):
    FAILED_ROWS_CACHE[upload_id] = failed_rows
    fpath = FAILED_ROWS_DIR / f"failed_rows_{upload_id}.json"
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(failed_rows, f)


def load_failed_rows(upload_id: int) -> List[Dict[str, Any]]:
    if upload_id in FAILED_ROWS_CACHE:
        return FAILED_ROWS_CACHE[upload_id]
    fpath = FAILED_ROWS_DIR / f"failed_rows_{upload_id}.json"
    if fpath.exists():
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            FAILED_ROWS_CACHE[upload_id] = data
            return data
    return []


@router.post("/sales")
def upload_sales(
    file: UploadFile = File(...),
    dataset_id: Optional[int] = Form(None),
    dataset_name: Optional[str] = Form(None),
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
        status="PROCESSING",
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

    raw_lines = text.splitlines()
    if raw_lines:
        first_line = raw_lines[0]
        header_cols = [c.strip() for c in first_line.split(",")]
        if "date" in header_cols and "date_" not in header_cols:
            header_cols = ["date_" if c == "date" else c for c in header_cols]
            text = "\n".join([",".join(header_cols)] + raw_lines[1:])

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

    # 1. Resolve target dataset for this upload
    if dataset_id is not None:
        target_dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not target_dataset:
            upload_job.status = "FAILED"
            upload_job.error_summary = f"Dataset id {dataset_id} not found."
            db.commit()
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found.")
    else:
        d_name = dataset_name or f"Upload: {file.filename} ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')})"
        target_dataset = Dataset(
            name=d_name,
            source="upload",
            is_active=True,
            row_count=0
        )
        db.add(target_dataset)
        db.commit()
        db.refresh(target_dataset)

    # 2. Prepare SKU mapping and lookup tables
    existing_products = db.query(Product).all()
    exact_product_ids = {str(p.product_id): p for p in existing_products}
    normalized_products = {str(p.product_id).strip().upper(): p for p in existing_products}

    total_rows = 0
    valid_rows = 0

    error_breakdown = {
        "unmapped_sku": 0,
        "bad_date": 0,
        "negative_qty": 0,
        "missing_qty": 0,
        "invalid_qty": 0,
        "negative_price": 0,
        "missing_price": 0,
        "invalid_price": 0,
        "duplicate_row": 0,
    }

    sample_errors = []
    unmapped_skus = set()
    suggested_mappings = []
    seen_proposed_skus = set()
    failed_rows_list = []

    seen_rows = set()
    sales_batch = []
    agg_map = {}
    BATCH_SIZE = 1000

    min_date = None
    max_date = None

    lines = list(csv.DictReader(text.splitlines()))
    total_rows = len(lines)

    for row_idx, row in enumerate(lines, start=1):
        raw_row = dict(row)
        for col in IGNORED_COLUMNS:
            row.pop(col, None)

        primary_error = None
        error_detail = None

        # Validate Date
        date_value = (row.get("date_") or "").strip()
        parsed_date = parse_date(date_value) if date_value else None
        if not date_value or parsed_date is None:
            primary_error = "bad_date"
            error_detail = {"row_number": row_idx, "column": "date_", "value": date_value, "message": "Invalid or missing date"}

        # Validate SKU
        product_value = (row.get("product_id") or "").strip()
        resolved_product_id = None

        if not primary_error:
            if not product_value:
                primary_error = "unmapped_sku"
                error_detail = {"row_number": row_idx, "column": "product_id", "value": product_value, "message": "Empty product_id"}
                unmapped_skus.add("EMPTY")
            elif product_value in exact_product_ids:
                resolved_product_id = product_value
            elif product_value.upper() in normalized_products:
                resolved_product_id = normalized_products[product_value.upper()].product_id
            else:
                best_match = None
                best_score = 0.0
                for p in existing_products:
                    score = rapidfuzz.fuzz.token_sort_ratio(product_value, p.product_name)
                    if score > best_score:
                        best_score = score
                        best_match = p

                if best_score >= 88 and best_match and product_value not in seen_proposed_skus:
                    seen_proposed_skus.add(product_value)
                    suggested_mappings.append({
                        "external_sku": product_value,
                        "suggested_product_id": str(best_match.product_id),
                        "product_name": best_match.product_name,
                        "confidence": round(best_score / 100.0, 2)
                    })

                if settings.AUTO_CREATE_UNKNOWN_SKUS:
                    new_prod = Product(
                        product_id=product_value,
                        product_name=product_value,
                        l0_category="Uncategorized",
                        is_provisional=True,
                        source_upload_job_id=upload_job.id,
                        is_active=True
                    )
                    db.add(new_prod)
                    db.flush()
                    exact_product_ids[product_value] = new_prod
                    normalized_products[product_value.upper()] = new_prod
                    existing_products.append(new_prod)
                    resolved_product_id = product_value

                    sku_map = SkuMapping(
                        dataset_id=target_dataset.id,
                        external_sku=product_value,
                        internal_product_id=product_value,
                        confidence=1.0,
                        mapping_method="exact"
                    )
                    db.add(sku_map)
                else:
                    primary_error = "unmapped_sku"
                    error_detail = {"row_number": row_idx, "column": "product_id", "value": product_value, "message": "Unknown product SKU"}
                    unmapped_skus.add(product_value)

        # Validate Quantity
        quantity = None
        if not primary_error:
            quantity_value = (row.get("procured_quantity") or "").strip()
            quantity = parse_float(quantity_value) if quantity_value else None
            if not quantity_value:
                primary_error = "missing_qty"
                error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": quantity_value, "message": "Missing procured_quantity"}
            elif quantity is None:
                primary_error = "invalid_qty"
                error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": quantity_value, "message": "Non-numeric quantity"}
            elif quantity < 0:
                primary_error = "negative_qty"
                error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": quantity_value, "message": "Quantity cannot be negative"}

        # Validate Price
        price = None
        if not primary_error:
            price_value = (row.get("unit_selling_price") or "").strip()
            price = parse_float(price_value) if price_value else None
            if not price_value:
                primary_error = "missing_price"
                error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_value, "message": "Missing unit_selling_price"}
            elif price is None:
                primary_error = "invalid_price"
                error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_value, "message": "Non-numeric unit_selling_price"}
            elif price < 0:
                primary_error = "negative_price"
                error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_value, "message": "Price cannot be negative"}

        # Check Duplicates
        if not primary_error:
            duplicate_key = tuple(row.get(k) for k in sorted(REQUIRED_COLUMNS if REQUIRED_COLUMNS.issubset(row.keys()) else row.keys()))
            if duplicate_key in seen_rows:
                primary_error = "duplicate_row"
                error_detail = {"row_number": row_idx, "column": "row", "value": str(duplicate_key[:3]), "message": "Duplicate row"}
            else:
                seen_rows.add(duplicate_key)

        if primary_error:
            error_breakdown[primary_error] += 1
            if len(sample_errors) < 10 and error_detail:
                sample_errors.append(error_detail)
            raw_row["error_reason"] = primary_error
            failed_rows_list.append(raw_row)
            continue

        valid_rows += 1
        city = row.get("city_name", "ALL")
        discount = parse_float(row.get("total_discount_amount")) or 0.0

        if min_date is None or parsed_date < min_date:
            min_date = parsed_date
        if max_date is None or parsed_date > max_date:
            max_date = parsed_date

        transaction = SalesTransaction(
            dataset_id=target_dataset.id,
            upload_id=upload_job.id,
            upload_job_id=upload_job.id,
            date_=parsed_date,
            city_name=city,
            order_id=row.get("order_id"),
            cart_id=row.get("cart_id"),
            dim_customer_key=row.get("dim_customer_key"),
            procured_quantity=quantity,
            unit_selling_price=price,
            total_discount_amount=discount,
            product_id=resolved_product_id,
            total_weighted_landing_price=parse_float(row.get("total_weighted_landing_price")),
        )
        sales_batch.append(transaction)

        agg_key = (parsed_date, resolved_product_id, city)
        if agg_key not in agg_map:
            agg_map[agg_key] = {"quantity": 0.0, "revenue": 0.0, "discount": 0.0, "orders": set()}
        agg_map[agg_key]["quantity"] += quantity
        agg_map[agg_key]["revenue"] += (quantity * price)
        agg_map[agg_key]["discount"] += discount
        if row.get("order_id"):
            agg_map[agg_key]["orders"].add(row.get("order_id"))

        if len(sales_batch) >= BATCH_SIZE:
            db.add_all(sales_batch)
            db.flush()
            sales_batch.clear()

    # Save failed rows for download/resolution
    if failed_rows_list:
        save_failed_rows(upload_job.id, failed_rows_list)

    # 3. HARD FAILURE ON EMPTY RESULT (valid_rows == 0)
    if valid_rows == 0:
        upload_job.total_rows = total_rows
        upload_job.processed_rows = 0
        upload_job.status = "FAILED"
        upload_job.error_summary = "No valid rows found in uploaded file."
        db.commit()

        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "reason": "no_valid_rows",
                "upload_id": upload_job.id,
                "total_rows": total_rows,
                "valid_rows": 0,
                "invalid_rows": total_rows,
                "error_breakdown": error_breakdown,
                "sample_errors": sample_errors[:10],
                "unmapped_skus": list(unmapped_skus)[:50],
                "suggested_mappings": suggested_mappings[:50]
            }
        )

    # Flush remaining transactions
    if sales_batch:
        db.add_all(sales_batch)
        db.flush()
        sales_batch.clear()

    # Upsert into DailyProductDemand (scoped to target_dataset.id)
    touched_product_ids = set()
    for (d_date, p_id, city), metrics in agg_map.items():
        touched_product_ids.add(p_id)
        existing = db.query(DailyProductDemand).filter(
            DailyProductDemand.dataset_id == target_dataset.id,
            DailyProductDemand.date_ == d_date,
            DailyProductDemand.product_id == p_id,
            DailyProductDemand.city_name == city
        ).first()

        if existing:
            existing.total_quantity = metrics["quantity"]
            existing.total_sales_value = metrics["revenue"]
            existing.total_discount_value = metrics["discount"]
            existing.order_count = len(metrics["orders"])
            existing.upload_job_id = upload_job.id
            if existing.total_quantity > 0:
                existing.avg_unit_price = round(existing.total_sales_value / existing.total_quantity, 2)
        else:
            unit_p = round(metrics["revenue"] / metrics["quantity"], 2) if metrics["quantity"] > 0 else 0.0
            new_demand = DailyProductDemand(
                dataset_id=target_dataset.id,
                upload_job_id=upload_job.id,
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

    # Invalidate downstream results for touched SKUs (Prompt 1.4)
    if touched_product_ids:
        # Mark forecast items / runs stale
        stale_run_ids = (
            db.query(ForecastItem.run_id)
            .filter(
                ForecastItem.dataset_id == target_dataset.id,
                ForecastItem.product_id.in_(touched_product_ids)
            )
            .distinct()
            .all()
        )
        run_ids = [r[0] for r in stale_run_ids]
        if run_ids:
            db.query(ForecastRun).filter(ForecastRun.id.in_(run_ids)).update({"is_stale": True}, synchronize_session=False)

        # Mark inventory recommendations stale
        db.query(InventoryRecommendation).filter(
            InventoryRecommendation.dataset_id == target_dataset.id,
            InventoryRecommendation.product_id.in_(touched_product_ids)
        ).update({"is_stale": True}, synchronize_session=False)

        # Mark anomalies stale
        db.query(AnomalyAlert).filter(
            AnomalyAlert.dataset_id == target_dataset.id,
            AnomalyAlert.product_id.in_(touched_product_ids)
        ).update({"is_stale": True}, synchronize_session=False)

    # Status check: COMPLETED (100% valid), PARTIAL (some valid, some invalid), REJECTED (0 valid)
    if valid_rows == 0:
        upload_job.status = "REJECTED"
    elif valid_rows < total_rows:
        upload_job.status = "PARTIAL"
    else:
        upload_job.status = "COMPLETED"

    upload_job.total_rows = total_rows
    upload_job.processed_rows = valid_rows
    upload_job.completed_at = datetime.now(timezone.utc)

    # Update dataset summary
    target_dataset.row_count = (target_dataset.row_count or 0) + valid_rows
    if min_date and (target_dataset.date_min is None or min_date < target_dataset.date_min):
        target_dataset.date_min = min_date
    if max_date and (target_dataset.date_max is None or max_date > target_dataset.date_max):
        target_dataset.date_max = max_date

    # Validation records
    validation_checks = [
        ("required_columns", "PASS", "All required columns are present."),
        ("date_validation", "PASS" if error_breakdown["bad_date"] == 0 else "WARNING", f"Bad dates: {error_breakdown['bad_date']}"),
        ("sku_validation", "PASS" if error_breakdown["unmapped_sku"] == 0 else "WARNING", f"Unmapped SKUs: {error_breakdown['unmapped_sku']}"),
        ("quantity_validation", "PASS" if (error_breakdown["negative_qty"] + error_breakdown["invalid_qty"] + error_breakdown["missing_qty"]) == 0 else "WARNING", f"Qty errors: {error_breakdown['negative_qty'] + error_breakdown['invalid_qty'] + error_breakdown['missing_qty']}"),
        ("price_validation", "PASS" if (error_breakdown["negative_price"] + error_breakdown["invalid_price"] + error_breakdown["missing_price"]) == 0 else "WARNING", f"Price errors: {error_breakdown['negative_price'] + error_breakdown['invalid_price'] + error_breakdown['missing_price']}"),
    ]
    for check_name, check_status, details in validation_checks:
        db.add(ValidationResult(upload_id=upload_job.id, check_name=check_name, status=check_status, details=details))

    db.commit()

    # Sync Parquet to DuckDB OLAP (Prompt 1.5)
    try:
        sync_dataset_to_duckdb(target_dataset.id, db)
    except Exception as d_err:
        print(f"DuckDB Parquet sync notice: {d_err}")

    # Trigger elasticity retrain
    try:
        from analytics.price_elasticity_engine import PriceElasticityEngine
        PriceElasticityEngine().run_analysis()
    except Exception as pe_err:
        print(f"Background elasticity auto-retrain trigger: {pe_err}")

    return {
        "upload_id": upload_job.id,
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "filename": upload_job.filename,
        "status": upload_job.status,
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": total_rows - valid_rows,
        "error_rows": total_rows - valid_rows,
        "error_breakdown": error_breakdown,
        "sample_errors": sample_errors[:10],
        "unmapped_skus": list(unmapped_skus)[:50],
        "suggested_mappings": suggested_mappings[:50],
        "message": "File processed successfully.",
        "created_at": upload_job.created_at,
    }


@router.get("/{upload_id}/failed-rows")
def download_failed_rows(upload_id: int, db: Session = Depends(get_db)):
    """
    Downloads original CSV rows that failed validation, with an appended error_reason column.
    """
    failed_rows = load_failed_rows(upload_id)
    if not failed_rows:
        raise HTTPException(status_code=404, detail="No failed rows found for this upload job.")

    output = io.StringIO()
    # Collect all fieldnames
    fieldnames = list(failed_rows[0].keys())
    if "error_reason" not in fieldnames:
        fieldnames.append("error_reason")

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in failed_rows:
        writer.writerow(row)

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="failed_rows_upload_{upload_id}.csv"'
        }
    )


@router.post("/{upload_id}/resolve-skus")
def resolve_skus_and_reingest(
    upload_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Persists user SKU resolutions to sku_mappings and re-ingests previously failed rows.
    """
    upload_job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    if not upload_job:
        raise HTTPException(status_code=404, detail="Upload job not found.")

    failed_rows = load_failed_rows(upload_id)
    if not failed_rows:
        raise HTTPException(status_code=400, detail="No failed rows available to resolve.")

    mappings = payload.get("mappings", [])
    if not mappings:
        raise HTTPException(status_code=400, detail="No SKU mappings provided.")

    # Find the dataset associated with this upload
    sample_tx = db.query(SalesTransaction).filter(SalesTransaction.upload_job_id == upload_id).first()
    if sample_tx:
        dataset_id = sample_tx.dataset_id
    else:
        dataset = resolve_dataset(db, None, None)
        dataset_id = dataset.id

    mapping_dict = {}
    for m in mappings:
        ext_sku = m.get("external_sku") or m.get("raw_sku") or m.get("sku")
        action = m.get("action") or ("create_new" if m.get("create_new") else "map")
        int_id = m.get("internal_product_id") or m.get("resolved_product_id")

        if not ext_sku:
            continue

        if action == "create_new" or not int_id:
            # Create provisional product
            int_id = ext_sku
            prod = db.query(Product).filter(Product.product_id == int_id).first()
            if not prod:
                new_p = Product(
                    product_id=int_id,
                    product_name=ext_sku,
                    l0_category="Uncategorized",
                    is_provisional=True,
                    source_upload_job_id=upload_job.id,
                    is_active=True
                )
                db.add(new_p)
                db.flush()

        # Add or update sku_mapping
        sku_map = db.query(SkuMapping).filter(
            SkuMapping.dataset_id == dataset_id,
            SkuMapping.external_sku == ext_sku
        ).first()

        if sku_map:
            sku_map.internal_product_id = int_id
            sku_map.mapping_method = "manual"
        else:
            sku_map = SkuMapping(
                dataset_id=dataset_id,
                external_sku=ext_sku,
                internal_product_id=int_id,
                confidence=1.0,
                mapping_method="manual"
            )
            db.add(sku_map)

        mapping_dict[ext_sku] = int_id

    db.commit()

    # Re-ingest failed rows matching the resolved SKUs
    still_failed = []
    reingested_count = 0
    new_sales = []
    agg_map = {}

    for row in failed_rows:
        ext_sku = (row.get("product_id") or "").strip()
        if ext_sku in mapping_dict and row.get("error_reason") == "unmapped_sku":
            resolved_pid = mapping_dict[ext_sku]
            parsed_d = parse_date(row.get("date_") or row.get("date"))
            qty = parse_float(row.get("procured_quantity"))
            price = parse_float(row.get("unit_selling_price"))
            disc = parse_float(row.get("total_discount_amount")) or 0.0

            if parsed_d and qty is not None and price is not None:
                city = row.get("city_name", "ALL")
                tx = SalesTransaction(
                    dataset_id=dataset_id,
                    upload_id=upload_job.id,
                    upload_job_id=upload_job.id,
                    date_=parsed_d,
                    city_name=city,
                    order_id=row.get("order_id"),
                    cart_id=row.get("cart_id"),
                    dim_customer_key=row.get("dim_customer_key"),
                    procured_quantity=qty,
                    unit_selling_price=price,
                    total_discount_amount=disc,
                    product_id=resolved_pid,
                    total_weighted_landing_price=parse_float(row.get("total_weighted_landing_price")),
                )
                new_sales.append(tx)
                reingested_count += 1

                agg_key = (parsed_d, resolved_pid, city)
                if agg_key not in agg_map:
                    agg_map[agg_key] = {"quantity": 0.0, "revenue": 0.0, "discount": 0.0, "orders": set()}
                agg_map[agg_key]["quantity"] += qty
                agg_map[agg_key]["revenue"] += (qty * price)
                agg_map[agg_key]["discount"] += disc
                if row.get("order_id"):
                    agg_map[agg_key]["orders"].add(row.get("order_id"))
                continue

        still_failed.append(row)

    if new_sales:
        db.add_all(new_sales)

    for (d_date, p_id, city), metrics in agg_map.items():
        existing = db.query(DailyProductDemand).filter(
            DailyProductDemand.dataset_id == dataset_id,
            DailyProductDemand.date_ == d_date,
            DailyProductDemand.product_id == p_id,
            DailyProductDemand.city_name == city
        ).first()

        if existing:
            existing.total_quantity += metrics["quantity"]
            existing.total_sales_value += metrics["revenue"]
            existing.total_discount_value += metrics["discount"]
            existing.order_count += len(metrics["orders"])
            if existing.total_quantity > 0:
                existing.avg_unit_price = round(existing.total_sales_value / existing.total_quantity, 2)
        else:
            unit_p = round(metrics["revenue"] / metrics["quantity"], 2) if metrics["quantity"] > 0 else 0.0
            new_demand = DailyProductDemand(
                dataset_id=dataset_id,
                upload_job_id=upload_job.id,
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

    # Update upload job and failed rows cache
    upload_job.processed_rows = (upload_job.processed_rows or 0) + reingested_count
    if len(still_failed) == 0:
        upload_job.status = "COMPLETED"
    elif upload_job.processed_rows > 0:
        upload_job.status = "PARTIAL"
    upload_job.completed_at = datetime.now(timezone.utc)

    save_failed_rows(upload_job.id, still_failed)
    db.commit()

    # Re-sync Parquet
    try:
        sync_dataset_to_duckdb(dataset_id, db)
    except Exception:
        pass

    return {
        "status": "success",
        "job_status": upload_job.status,
        "re_ingested_rows": reingested_count,
        "reingested_rows": reingested_count,
        "remaining_errors": len(still_failed),
        "remaining_failed_rows": len(still_failed),
        "total_valid_rows": upload_job.processed_rows,
        "message": f"Successfully resolved and ingested {reingested_count} rows."
    }


@router.get("/uploads")
def get_uploads(db: Session = Depends(get_db)):
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
def get_upload(upload_id: int, db: Session = Depends(get_db)):
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
def get_validation_results(upload_id: int, db: Session = Depends(get_db)):
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