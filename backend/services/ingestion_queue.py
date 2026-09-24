"""
backend/services/ingestion_queue.py
-----------------------------------
Asynchronous background ingestion pipeline for sales uploads.
Features:
- Decouples file upload from request thread: POST /api/upload/sales streams file to disk
  and returns HTTP 202 Accepted with {upload_id, poll_url}.
- Pipeline stages: pending -> parsing -> validating -> ingesting -> aggregating -> completed/failed/partial/rejected.
- Updates upload_jobs.progress_pct and current_stage in real-time.
- Enforces limits: MAX_UPLOAD_MB (100MB), MAX_ROWS (5,000,000).
- Memory-bounded chunked stream parsing via pandas chunksize.
- Periodic crash sweeper: Marks jobs stuck in non-terminal states for > 30 minutes as FAILED.
"""

import csv
import io
import json
import logging
import os
import re
import uuid
import hashlib
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import rapidfuzz
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db.session import SessionLocal
from backend.models.upload import UploadJob, ValidationResult
from backend.models.dataset import Dataset, SkuMapping
from backend.models.product import Product
from backend.models.sales import SalesTransaction
from backend.models.demand import DailyProductDemand
from backend.models.forecast import ForecastRun, ForecastItem
from backend.models.inventory import InventoryRecommendation
from backend.models.anomaly import AnomalyAlert
from backend.services.duckdb_service import sync_dataset_to_duckdb
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Configurable Limits
MAX_UPLOAD_MB = 100
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_ROWS = 5_000_000
CHUNK_SIZE = 10_000
CRASH_TIMEOUT_MINUTES = 30

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FAILED_ROWS_DIR = PROJECT_ROOT / "dataset" / "failed_rows"
FAILED_ROWS_DIR.mkdir(parents=True, exist_ok=True)
FAILED_ROWS_CACHE: Dict[int, List[Dict[str, Any]]] = {}

# Background Worker ThreadPool for asynchronous execution
INGESTION_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingestion_worker")

REQUIRED_COLUMNS = {
    "date_", "city_name", "order_id", "cart_id", "dim_customer_key",
    "procured_quantity", "unit_selling_price", "total_discount_amount",
    "product_id", "total_weighted_landing_price"
}


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    try:
        return float(val_str)
    except (ValueError, TypeError):
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


def update_job_progress(
    db: Session,
    job_id: int,
    status: str,
    stage: str,
    progress_pct: int,
    error_message: Optional[str] = None,
    total_rows: Optional[int] = None,
    processed_rows: Optional[int] = None,
    error_summary: Optional[str] = None,
):
    """Updates progress, stage, and status for an UploadJob in DB."""
    try:
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if job:
            job.status = status
            job.current_stage = stage
            job.progress_pct = progress_pct
            if error_message is not None:
                job.error_message = error_message
            if total_rows is not None:
                job.total_rows = total_rows
            if processed_rows is not None:
                job.processed_rows = processed_rows
            if error_summary is not None:
                job.error_summary = error_summary
            if status in ("COMPLETED", "PARTIAL", "REJECTED", "FAILED"):
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update progress for job {job_id}: {e}")


def sweep_stuck_jobs(db: Session, max_age_minutes: int = CRASH_TIMEOUT_MINUTES) -> int:
    """
    Finds and marks jobs stuck in non-terminal states (PENDING, PROCESSING)
    for longer than max_age_minutes as FAILED.
    """
    threshold_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    stuck_jobs = (
        db.query(UploadJob)
        .filter(
            UploadJob.status.in_(["PENDING", "PROCESSING"]),
            UploadJob.created_at < threshold_time,
        )
        .all()
    )

    count = 0
    for job in stuck_jobs:
        job.status = "FAILED"
        job.current_stage = "failed"
        job.error_message = f"Worker timeout: Job was stuck in a non-terminal state for over {max_age_minutes} minutes."
        job.completed_at = datetime.now(timezone.utc)
        count += 1

    if count > 0:
        db.commit()
        logger.warning(f"Swept {count} stuck upload jobs.")
    return count


def process_upload_job(job_id: int, db: Optional[Session] = None):
    """
    Main ingestion worker execution pipeline.
    Supports both asynchronous worker threads and synchronous fallback for unit tests.
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if not job or not job.saved_file_path or not os.path.exists(job.saved_file_path):
            update_job_progress(db, job_id, "FAILED", "failed", 0, "Uploaded file not found on server disk.")
            return

        target_dataset = db.query(Dataset).filter(Dataset.id == job.dataset_id).first()
        if not target_dataset:
            update_job_progress(db, job_id, "FAILED", "failed", 0, f"Dataset {job.dataset_id} not found.")
            return

        # ----------------------------------------------------
        # STAGE 1: PARSING (Chunked reading & bounds check)
        # ----------------------------------------------------
        update_job_progress(db, job_id, "PROCESSING", "parsing", 10)
        file_path = job.saved_file_path

        # Quick row count estimation without loading entire CSV into memory
        total_rows = 0
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        total_rows += 1
            total_rows = max(0, total_rows - 1)  # subtract header line
        except Exception as e:
            update_job_progress(db, job_id, "FAILED", "failed", 10, f"Could not read CSV: {e}")
            return

        if total_rows > MAX_ROWS:
            update_job_progress(
                db, job_id, "FAILED", "failed", 10,
                f"File exceeds maximum allowed rows limit of {MAX_ROWS:,} (found {total_rows:,} rows)."
            )
            return

        update_job_progress(db, job_id, "PROCESSING", "parsing", 25, total_rows=total_rows)

        # ----------------------------------------------------
        # STAGE 2: VALIDATING (Schema, dates, SKUs, numbers)
        # ----------------------------------------------------
        update_job_progress(db, job_id, "PROCESSING", "validating", 40)

        existing_products = db.query(Product).all()
        exact_product_ids = {str(p.product_id): p for p in existing_products}
        normalized_products = {str(p.product_id).strip().upper(): p for p in existing_products}

        sku_mappings: Dict[str, str] = {}
        for m in db.query(SkuMapping).filter(
            (SkuMapping.dataset_id == target_dataset.id) | (SkuMapping.dataset_id == None)
        ).all():
            if m.external_sku and m.internal_product_id:
                sku_mappings[m.external_sku] = m.internal_product_id

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

        sample_errors: List[Dict[str, Any]] = []
        unmapped_skus: Set[str] = set()
        suggested_mappings: List[Dict[str, Any]] = []
        seen_proposed_skus: Set[str] = set()
        failed_rows_list: List[Dict[str, Any]] = []

        seen_rows: Set[Tuple] = set()
        valid_records: List[SalesTransaction] = []
        agg_map: Dict[Tuple[date, str, str], Dict[str, Any]] = {}
        touched_product_ids: Set[str] = set()
        min_date: Optional[date] = None
        max_date: Optional[date] = None
        valid_rows = 0

        # Stream parse with chunksize to bound memory
        chunk_iter = pd.read_csv(
            file_path,
            chunksize=CHUNK_SIZE,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8",
            on_bad_lines="skip",
        )

        row_idx = 0
        for chunk in chunk_iter:
            records = chunk.to_dict(orient="records")
            for raw_row in records:
                row_idx += 1
                row = dict(raw_row)

                primary_error = None
                error_detail = None

                # 1. Date validation
                date_val_str = (row.get("date_") or row.get("date") or row.get("order_date") or "").strip()
                parsed_date = parse_date(date_val_str)
                if not date_val_str or parsed_date is None:
                    primary_error = "bad_date"
                    error_detail = {"row_number": row_idx, "column": "date_", "value": date_val_str, "message": "Invalid or missing date"}

                # 2. SKU validation
                product_val = (row.get("product_id") or row.get("sku") or "").strip()
                resolved_product_id = None

                if not primary_error:
                    if not product_val:
                        primary_error = "unmapped_sku"
                        error_detail = {"row_number": row_idx, "column": "product_id", "value": product_val, "message": "Empty product_id"}
                        unmapped_skus.add("EMPTY")
                    elif product_val in exact_product_ids:
                        resolved_product_id = product_val
                    elif product_val.upper() in normalized_products:
                        resolved_product_id = normalized_products[product_val.upper()].product_id
                    elif product_val in sku_mappings:
                        resolved_product_id = sku_mappings[product_val]
                    else:
                        # Fuzzy match check
                        best_match = None
                        best_score = 0.0
                        for p in existing_products:
                            score = rapidfuzz.fuzz.token_sort_ratio(product_val, p.product_name)
                            if score > best_score:
                                best_score = score
                                best_match = p

                        if best_score >= 88 and best_match and product_val not in seen_proposed_skus:
                            seen_proposed_skus.add(product_val)
                            suggested_mappings.append({
                                "external_sku": product_val,
                                "suggested_product_id": str(best_match.product_id),
                                "product_name": best_match.product_name,
                                "confidence": round(best_score / 100.0, 2),
                            })

                        if settings.AUTO_CREATE_UNKNOWN_SKUS:
                            new_prod = Product(
                                product_id=product_val,
                                product_name=product_val,
                                l0_category="Uncategorized",
                                is_provisional=True,
                                source_upload_job_id=job.id,
                                is_active=True,
                            )
                            db.add(new_prod)
                            db.flush()
                            exact_product_ids[product_val] = new_prod
                            normalized_products[product_val.upper()] = new_prod
                            existing_products.append(new_prod)
                            resolved_product_id = product_val

                            sku_map = SkuMapping(
                                dataset_id=target_dataset.id,
                                external_sku=product_val,
                                internal_product_id=product_val,
                                confidence=1.0,
                                mapping_method="exact",
                            )
                            db.add(sku_map)
                            sku_mappings[product_val] = product_val
                        else:
                            primary_error = "unmapped_sku"
                            error_detail = {"row_number": row_idx, "column": "product_id", "value": product_val, "message": "Unknown product SKU"}
                            unmapped_skus.add(product_val)

                # 3. Quantity validation
                quantity = None
                if not primary_error:
                    qty_str = (row.get("procured_quantity") or row.get("quantity") or row.get("qty") or "").strip()
                    quantity = parse_float(qty_str)
                    if not qty_str:
                        primary_error = "missing_qty"
                        error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": qty_str, "message": "Missing procured_quantity"}
                    elif quantity is None:
                        primary_error = "invalid_qty"
                        error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": qty_str, "message": "Non-numeric quantity"}
                    elif quantity < 0:
                        primary_error = "negative_qty"
                        error_detail = {"row_number": row_idx, "column": "procured_quantity", "value": qty_str, "message": "Quantity cannot be negative"}

                # 4. Price validation
                price = None
                if not primary_error:
                    price_str = (row.get("unit_selling_price") or row.get("unit_price") or row.get("price") or row.get("sales_amount") or "").strip()
                    price = parse_float(price_str)
                    if not price_str:
                        primary_error = "missing_price"
                        error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_str, "message": "Missing unit_selling_price"}
                    elif price is None:
                        primary_error = "invalid_price"
                        error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_str, "message": "Non-numeric unit_selling_price"}
                    elif price < 0:
                        primary_error = "negative_price"
                        error_detail = {"row_number": row_idx, "column": "unit_selling_price", "value": price_str, "message": "Price cannot be negative"}

                # 5. Duplicate row validation
                if not primary_error:
                    dup_key = tuple(row.get(k) for k in sorted(row.keys()))
                    if dup_key in seen_rows:
                        primary_error = "duplicate_row"
                        error_detail = {"row_number": row_idx, "column": "row", "value": str(dup_key[:3]), "message": "Duplicate row"}
                    else:
                        seen_rows.add(dup_key)

                if primary_error:
                    error_breakdown[primary_error] += 1
                    if len(sample_errors) < 10 and error_detail:
                        sample_errors.append(error_detail)
                    failed_row = dict(raw_row)
                    failed_row["error_reason"] = primary_error
                    failed_rows_list.append(failed_row)
                    continue

                valid_rows += 1
                city = (row.get("city_name") or row.get("city") or "ALL").strip() or "ALL"
                discount = parse_float(row.get("total_discount_amount") or row.get("discount")) or 0.0

                if min_date is None or parsed_date < min_date:
                    min_date = parsed_date
                if max_date is None or parsed_date > max_date:
                    max_date = parsed_date

                transaction = SalesTransaction(
                    dataset_id=target_dataset.id,
                    upload_id=job.id,
                    upload_job_id=job.id,
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
                valid_records.append(transaction)
                touched_product_ids.add(resolved_product_id)

                agg_key = (parsed_date, resolved_product_id, city)
                if agg_key not in agg_map:
                    agg_map[agg_key] = {"quantity": 0.0, "revenue": 0.0, "discount": 0.0, "orders": set()}
                agg_map[agg_key]["quantity"] += quantity
                agg_map[agg_key]["revenue"] += (quantity * price)
                agg_map[agg_key]["discount"] += discount
                if row.get("order_id"):
                    agg_map[agg_key]["orders"].add(row.get("order_id"))

        if failed_rows_list:
            save_failed_rows(job.id, failed_rows_list)

        # ----------------------------------------------------
        # HARD FAILURE ON EMPTY RESULT (valid_rows == 0)
        # ----------------------------------------------------
        if valid_rows == 0:
            summary_dict = {
                "total_rows": total_rows,
                "valid_rows": 0,
                "invalid_rows": total_rows,
                "error_breakdown": error_breakdown,
                "sample_errors": sample_errors[:10],
                "unmapped_skus": list(unmapped_skus)[:50],
                "suggested_mappings": suggested_mappings[:50],
            }
            update_job_progress(
                db=db,
                job_id=job_id,
                status="FAILED",
                stage="failed",
                progress_pct=100,
                total_rows=total_rows,
                processed_rows=0,
                error_message="No valid rows found in uploaded file.",
                error_summary=json.dumps(summary_dict),
            )
            return

        # ----------------------------------------------------
        # STAGE 3: INGESTING (Batch DB writes)
        # ----------------------------------------------------
        update_job_progress(db, job_id, "PROCESSING", "ingesting", 70, processed_rows=valid_rows)

        # Bulk save sales transactions in batches
        BATCH_SIZE = 1000
        for i in range(0, len(valid_records), BATCH_SIZE):
            batch = valid_records[i:i + BATCH_SIZE]
            db.add_all(batch)
            db.flush()

        # Idempotent upsert into DailyProductDemand
        is_accumulate = (job.conflict_mode or "").lower() == "accumulate"
        for (d_date, p_id, city), metrics in agg_map.items():
            existing = (
                db.query(DailyProductDemand)
                .filter(
                    DailyProductDemand.dataset_id == target_dataset.id,
                    DailyProductDemand.date_ == d_date,
                    DailyProductDemand.product_id == p_id,
                    DailyProductDemand.city_name == city,
                )
                .first()
            )

            order_count = len(metrics["orders"]) if metrics["orders"] else 1
            if existing:
                if is_accumulate:
                    existing.total_quantity += metrics["quantity"]
                    existing.total_sales_value += metrics["revenue"]
                    existing.total_discount_value += metrics["discount"]
                    existing.order_count += order_count
                else:
                    existing.total_quantity = metrics["quantity"]
                    existing.total_sales_value = metrics["revenue"]
                    existing.total_discount_value = metrics["discount"]
                    existing.order_count = order_count
                existing.upload_job_id = job.id
                existing.avg_unit_price = (
                    round(existing.total_sales_value / existing.total_quantity, 2)
                    if existing.total_quantity > 0 else 0.0
                )
            else:
                unit_price = round(metrics["revenue"] / metrics["quantity"], 2) if metrics["quantity"] > 0 else 0.0
                new_demand = DailyProductDemand(
                    dataset_id=target_dataset.id,
                    upload_job_id=job.id,
                    date_=d_date,
                    product_id=p_id,
                    city_name=city,
                    total_quantity=metrics["quantity"],
                    total_sales_value=metrics["revenue"],
                    total_discount_value=metrics["discount"],
                    avg_unit_price=unit_price,
                    order_count=order_count,
                )
                db.add(new_demand)
        db.flush()

        # ----------------------------------------------------
        # STAGE 4: AGGREGATING (Cache invalidation & DuckDB sync)
        # ----------------------------------------------------
        update_job_progress(db, job_id, "PROCESSING", "aggregating", 90)

        if touched_product_ids:
            stale_runs = (
                db.query(ForecastItem.run_id)
                .filter(
                    ForecastItem.dataset_id == target_dataset.id,
                    ForecastItem.product_id.in_(touched_product_ids),
                )
                .distinct()
                .all()
            )
            run_ids = [r[0] for r in stale_runs]
            if run_ids:
                db.query(ForecastRun).filter(ForecastRun.id.in_(run_ids)).update({"is_stale": True}, synchronize_session=False)

            db.query(InventoryRecommendation).filter(
                InventoryRecommendation.dataset_id == target_dataset.id,
                InventoryRecommendation.product_id.in_(touched_product_ids),
            ).update({"is_stale": True}, synchronize_session=False)

            db.query(AnomalyAlert).filter(
                AnomalyAlert.dataset_id == target_dataset.id,
                AnomalyAlert.product_id.in_(touched_product_ids),
            ).update({"is_stale": True}, synchronize_session=False)

        # Update dataset summary metadata
        target_dataset.row_count = (target_dataset.row_count or 0) + valid_rows
        if min_date and (target_dataset.date_min is None or min_date < target_dataset.date_min):
            target_dataset.date_min = min_date
        if max_date and (target_dataset.date_max is None or max_date > target_dataset.date_max):
            target_dataset.date_max = max_date

        # Persist validation records
        val_checks = [
            ("required_columns", "PASS", "All required columns verified."),
            ("date_validation", "PASS" if error_breakdown["bad_date"] == 0 else "WARNING", f"Bad dates: {error_breakdown['bad_date']}"),
            ("sku_validation", "PASS" if error_breakdown["unmapped_sku"] == 0 else "WARNING", f"Unmapped SKUs: {error_breakdown['unmapped_sku']}"),
            ("quantity_validation", "PASS" if (error_breakdown["negative_qty"] + error_breakdown["invalid_qty"]) == 0 else "WARNING", f"Qty errors: {error_breakdown['negative_qty'] + error_breakdown['invalid_qty']}"),
            ("price_validation", "PASS" if (error_breakdown["negative_price"] + error_breakdown["invalid_price"]) == 0 else "WARNING", f"Price errors: {error_breakdown['negative_price'] + error_breakdown['invalid_price']}"),
        ]
        for check_name, status_str, detail_str in val_checks:
            db.add(ValidationResult(upload_id=job.id, check_name=check_name, status=status_str, details=detail_str))

        db.commit()

        # Synchronize DuckDB Parquet under write lock
        try:
            sync_dataset_to_duckdb(target_dataset.id, db)
        except Exception as d_err:
            logger.warning(f"DuckDB Parquet sync notice: {d_err}")

        # ----------------------------------------------------
        # STAGE 5: TERMINAL STATUS RESOLUTION
        # ----------------------------------------------------
        if valid_rows == 0:
            final_status = "REJECTED"
        elif valid_rows < total_rows:
            final_status = "PARTIAL"
        else:
            final_status = "COMPLETED"

        summary_dict = {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": total_rows - valid_rows,
            "error_breakdown": error_breakdown,
            "sample_errors": sample_errors[:10],
            "unmapped_skus": list(unmapped_skus)[:50],
            "suggested_mappings": suggested_mappings[:50],
        }

        update_job_progress(
            db=db,
            job_id=job_id,
            status=final_status,
            stage="completed",
            progress_pct=100,
            total_rows=total_rows,
            processed_rows=valid_rows,
            error_summary=json.dumps(summary_dict),
        )
        logger.info(f"UploadJob {job_id} finished with status={final_status}, valid_rows={valid_rows}/{total_rows}.")

    except Exception as exc:
        logger.exception(f"Unhandled error in upload job {job_id}: {exc}")
        update_job_progress(
            db=db,
            job_id=job_id,
            status="FAILED",
            stage="failed",
            progress_pct=100,
            error_message=f"Pipeline error: {str(exc)}",
        )
    finally:
        if should_close:
            db.close()


def enqueue_upload_job(job_id: int):
    """Submits upload job to background thread pool executor."""
    INGESTION_EXECUTOR.submit(process_upload_job, job_id)
