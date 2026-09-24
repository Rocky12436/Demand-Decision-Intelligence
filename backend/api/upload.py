import csv
import io
import json
import uuid
import hashlib
import logging
import sys
import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query, Response, status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db.session import get_db, enforce_writable_db
from backend.models.user import User
from backend.core.deps import require_role, get_current_user_or_guest
from backend.core.rate_limit import rate_limit_upload
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
from backend.services.ingestion_queue import (
    enqueue_upload_job,
    process_upload_job,
    sweep_stuck_jobs,
    save_failed_rows,
    load_failed_rows,
    FAILED_ROWS_DIR,
    FAILED_ROWS_CACHE,
    MAX_UPLOAD_MB,
    MAX_UPLOAD_BYTES,
)

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = PROJECT_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_csv_cell(val: Any) -> Any:
    """Sanitizes cells on export to prevent CSV formula injection in Excel."""
    if isinstance(val, str) and len(val) > 0 and val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{val}"
    return val


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





def check_job_idor(job: UploadJob, user: Optional[User]):
    """
    IDOR Defense (Prompt 3.3 item 4):
    Verifies that the requested entity belongs to the user or dataset.
    Returns 404 (not 403) to avoid leaking entity existence.
    """
    if user and user.role and user.role.name.lower() != "admin":
        if job.uploaded_by_user_id and job.uploaded_by_user_id != user.id:
            raise HTTPException(status_code=404, detail=f"Upload job {job.id} not found.")


@router.post("/sales")
def upload_sales(
    file: UploadFile = File(...),
    dataset_id: Optional[int] = Form(None),
    dataset_name: Optional[str] = Form(None),
    create_new_dataset: Optional[bool] = Form(None),
    conflict_mode: Optional[str] = Form(None),
    allow_duplicate: Optional[bool] = Form(None),
    query_dataset_id: Optional[int] = Query(None, alias="dataset_id"),
    query_dataset_name: Optional[str] = Query(None, alias="dataset_name"),
    query_create_new_dataset: Optional[bool] = Query(None, alias="create_new_dataset"),
    query_conflict_mode: Optional[str] = Query(None, alias="conflict_mode"),
    query_allow_duplicate: Optional[bool] = Query(None, alias="allow_duplicate"),
    async_mode: Optional[bool] = Query(None),
    form_async_mode: Optional[bool] = Form(None, alias="async_mode"),
    current_user: Optional[User] = Depends(require_role(["admin", "manager"])),
    _rate_limit: None = Depends(rate_limit_upload),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db),
):
    eff_dataset_id = dataset_id if dataset_id is not None else query_dataset_id
    eff_dataset_name = dataset_name if dataset_name is not None else query_dataset_name
    raw_conflict = conflict_mode if conflict_mode is not None else (query_conflict_mode or "replace")
    raw_allow_dup = allow_duplicate if allow_duplicate is not None else (query_allow_duplicate or False)
    raw_create_new = create_new_dataset if create_new_dataset is not None else query_create_new_dataset

    # Determine effective async mode: True by default in browser/prod, sync in pytest unless explicit
    raw_async = form_async_mode if form_async_mode is not None else async_mode
    if raw_async is not None:
        if isinstance(raw_async, str):
            effective_async = raw_async.strip().lower() in ("true", "1", "yes")
        else:
            effective_async = bool(raw_async)
    else:
        if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
            effective_async = False
        else:
            effective_async = True

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    # 1. Stream file to disk outside web root with MAX_UPLOAD_MB enforcement
    safe_filename = f"upload_{uuid.uuid4().hex}.csv"
    safe_path = UPLOAD_DIR / safe_filename

    hasher = hashlib.sha256()
    total_bytes = 0

    file.file.seek(0)
    with open(safe_path, "wb") as out_f:
        while True:
            chunk = file.file.read(64 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                out_f.close()
                if safe_path.exists():
                    safe_path.unlink()
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum upload size limit of {MAX_UPLOAD_MB}MB."
                )
            hasher.update(chunk)
            out_f.write(chunk)

    file_hash = hasher.hexdigest()
    file_size = total_bytes

    try:
        with open(safe_path, "rb") as f_check:
            first_bytes = f_check.read(1024)
            text_preview = first_bytes.decode("utf-8-sig", errors="replace")
    except Exception:
        if safe_path.exists():
            safe_path.unlink()
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding.")

    conflict_mode_normalized = raw_conflict.strip().lower() if isinstance(raw_conflict, str) else "replace"
    if isinstance(raw_allow_dup, str):
        allow_duplicate_flag = raw_allow_dup.strip().lower() in ("true", "1", "yes")
    else:
        allow_duplicate_flag = bool(raw_allow_dup)

    if isinstance(raw_create_new, str):
        create_new_flag = raw_create_new.strip().lower() in ("true", "1", "yes")
    else:
        create_new_flag = bool(raw_create_new) if raw_create_new is not None else False

    # Resolve target dataset for this upload (Prompt Fix 1)
    target_dataset = None
    if eff_dataset_id is not None:
        target_dataset = db.query(Dataset).filter(Dataset.id == eff_dataset_id).first()
        if not target_dataset:
            if safe_path.exists():
                safe_path.unlink()
            raise HTTPException(status_code=404, detail=f"Dataset {eff_dataset_id} not found.")
    elif not create_new_flag:
        # 1. Check caller's active dataset if logged in
        if current_user and getattr(current_user, "active_dataset_id", None):
            target_dataset = db.query(Dataset).filter(
                Dataset.id == current_user.active_dataset_id,
                Dataset.is_active == True
            ).first()

        # 2. Check system default upload target
        if not target_dataset:
            target_dataset = db.query(Dataset).filter(
                Dataset.is_default_upload_target == True,
                Dataset.is_active == True
            ).order_by(Dataset.id.desc()).first()

        # 3. Check most recent active user dataset
        if not target_dataset and current_user and getattr(current_user, "id", None):
            target_dataset = db.query(Dataset).filter(
                Dataset.user_id == current_user.id,
                Dataset.is_active == True
            ).order_by(Dataset.id.desc()).first()

        # 4. Fallback to any non-seed active dataset
        if not target_dataset:
            target_dataset = db.query(Dataset).filter(
                Dataset.is_active == True,
                Dataset.name != "Demo Data",
                Dataset.source != "seed"
            ).order_by(Dataset.id.desc()).first()

    # Only create a brand new dataset if explicitly requested or if no active dataset exists at all
    if not target_dataset:
        d_name = eff_dataset_name or f"Upload: {file.filename} ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')})"
        # If there are existing datasets, unset is_default_upload_target on them
        db.query(Dataset).filter(Dataset.is_default_upload_target == True).update({"is_default_upload_target": False})
        target_dataset = Dataset(
            user_id=current_user.id if current_user else None,
            name=d_name,
            source="upload",
            is_active=True,
            is_default_upload_target=True,
            status="active",
            row_count=0
        )
        db.add(target_dataset)
        db.flush()

        if current_user:
            current_user.active_dataset_id = target_dataset.id
            db.flush()
    else:
        # Keep user active_dataset_id in sync
        if current_user and current_user.active_dataset_id != target_dataset.id:
            current_user.active_dataset_id = target_dataset.id
            db.flush()

    # Check for duplicate file hash in dataset (Prompt 1.6)
    existing_dup = (
        db.query(UploadJob)
        .filter(
            UploadJob.dataset_id == target_dataset.id,
            UploadJob.file_hash == file_hash,
            UploadJob.status.in_(["COMPLETED", "PARTIAL", "SUCCESS"]),
        )
        .first()
    )
    if existing_dup and not allow_duplicate_flag:
        if safe_path.exists():
            safe_path.unlink()
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"Duplicate file upload detected. File with SHA-256 {file_hash[:12]}... already ingested in Job #{existing_dup.id}.",
                "prior_job_id": existing_dup.id,
                "filename": existing_dup.filename,
                "file_hash": file_hash,
                "message": "This file has already been ingested. Provide allow_duplicate=true to re-upload anyway."
            }
        )

    upload_job = UploadJob(
        filename=file.filename,
        file_type="sales",
        file_size_bytes=file_size,
        dataset_id=target_dataset.id,
        file_hash=file_hash,
        conflict_mode=conflict_mode_normalized,
        status="PENDING",
        current_stage="pending",
        progress_pct=0,
        saved_file_path=str(safe_path),
        uploaded_by_user_id=current_user.id if current_user else None,
        total_rows=0,
        processed_rows=0,
    )
    db.add(upload_job)
    db.commit()
    db.refresh(upload_job)

    # Run crash sweeper for old stuck jobs
    sweep_stuck_jobs(db)

    if effective_async:
        # Enqueue worker
        enqueue_upload_job(upload_job.id)
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={
                "status": "pending",
                "upload_id": upload_job.id,
                "job_id": upload_job.id,
                "poll_url": f"/api/upload/{upload_job.id}/status",
                "message": "File upload accepted and queued for background ingestion."
            }
        )

    # If synchronous mode requested, process immediately
    process_upload_job(upload_job.id, db=db)
    db.refresh(upload_job)
    db.refresh(target_dataset)

    summary = json.loads(upload_job.error_summary) if upload_job.error_summary else {}

    # Handle hard failure on empty result (valid_rows == 0) in sync mode
    if upload_job.processed_rows == 0:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "reason": "no_valid_rows",
                "upload_id": upload_job.id,
                "total_rows": upload_job.total_rows or 0,
                "valid_rows": 0,
                "invalid_rows": upload_job.total_rows or 0,
                "error_breakdown": summary.get("error_breakdown", {}),
                "sample_errors": summary.get("sample_errors", [])[:10],
                "unmapped_skus": summary.get("unmapped_skus", [])[:50],
                "suggested_mappings": summary.get("suggested_mappings", [])[:50]
            }
        )

    return {
        "upload_id": upload_job.id,
        "dataset_id": target_dataset.id,
        "dataset_name": target_dataset.name,
        "filename": upload_job.filename,
        "status": upload_job.status,
        "total_rows": upload_job.total_rows,
        "valid_rows": upload_job.processed_rows,
        "invalid_rows": (upload_job.total_rows or 0) - (upload_job.processed_rows or 0),
        "error_rows": (upload_job.total_rows or 0) - (upload_job.processed_rows or 0),
        "error_breakdown": summary.get("error_breakdown", {}),
        "sample_errors": summary.get("sample_errors", [])[:10],
        "unmapped_skus": summary.get("unmapped_skus", [])[:50],
        "file_hash": file_hash,
        "conflict_mode": conflict_mode_normalized,
        "message": "File processed successfully.",
        "created_at": upload_job.created_at,
    }



@router.get("/{job_id}/status", summary="Get Upload Job Status and Progress")
def get_upload_status(
    job_id: int,
    current_user: Optional[User] = Depends(get_current_user_or_guest),
    db: Session = Depends(get_db)
):
    """
    Returns the real-time background ingestion progress, stage, and completion status.
    """
    sweep_stuck_jobs(db)
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Upload job {job_id} not found.")

    check_job_idor(job, current_user)

    summary = None
    if job.error_summary:
        try:
            summary = json.loads(job.error_summary)
        except Exception:
            pass

    return {
        "upload_id": job.id,
        "job_id": job.id,
        "dataset_id": job.dataset_id,
        "filename": job.filename,
        "status": job.status,
        "current_stage": job.current_stage or "pending",
        "progress_pct": job.progress_pct,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "valid_rows": job.processed_rows,
        "invalid_rows": (job.total_rows or 0) - (job.processed_rows or 0),
        "error_rows": (job.total_rows or 0) - (job.processed_rows or 0),
        "error_message": job.error_message,
        "error_summary": summary,
        "error_breakdown": summary.get("error_breakdown", {}) if summary else {},
        "sample_errors": summary.get("sample_errors", [])[:10] if summary else [],
        "unmapped_skus": summary.get("unmapped_skus", [])[:50] if summary else [],
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "poll_url": f"/api/upload/{job.id}/status",
    }


@router.get("/{upload_id}/failed-rows")
def download_failed_rows(
    upload_id: int,
    current_user: Optional[User] = Depends(get_current_user_or_guest),
    db: Session = Depends(get_db)
):
    """
    Downloads original CSV rows that failed validation, with an appended error_reason column.
    Sanitizes formula injection (=, +, -, @, tab, CR) by prefixing a single quote.
    """
    job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found.")

    check_job_idor(job, current_user)

    failed_rows = load_failed_rows(upload_id)
    if not failed_rows:
        raise HTTPException(status_code=404, detail="No failed rows found for this upload job.")

    output = io.StringIO()
    fieldnames = list(failed_rows[0].keys())
    if "error_reason" not in fieldnames:
        fieldnames.append("error_reason")

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in failed_rows:
        # Prompt 3.3 item 5: CSV Injection defense
        sanitized = {k: sanitize_csv_cell(v) for k, v in row.items()}
        writer.writerow(sanitized)

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
    _role_check: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
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


@router.delete("/uploads/{upload_id}")
@router.delete("/{upload_id}")
def delete_upload_job(
    upload_id: int,
    _role_check: Optional[User] = Depends(require_role(["admin", "manager"])),
    _writable: None = Depends(enforce_writable_db),
    db: Session = Depends(get_db)
):
    """
    Deletes an upload job and rolls back all data it created:
    - Removes sales_transactions created by this job
    - Recalculates or deletes affected daily_product_demand rows
    - Marks dependent forecast_runs, inventory_recommendations, anomalies as stale
    - Re-syncs DuckDB Parquet
    - Deletes the upload_job record
    """
    upload_job = db.query(UploadJob).filter(UploadJob.id == upload_id).first()
    if not upload_job:
        raise HTTPException(status_code=404, detail=f"Upload job {upload_id} not found.")

    dataset_id = upload_job.dataset_id

    # 1. Fetch transactions created by this job
    transactions = (
        db.query(SalesTransaction)
        .filter(
            (SalesTransaction.upload_job_id == upload_id) | (SalesTransaction.upload_id == upload_id)
        )
        .all()
    )

    affected_keys = set()
    affected_products = set()
    for tx in transactions:
        d_id = tx.dataset_id or dataset_id
        if d_id:
            affected_keys.add((d_id, tx.date_, tx.product_id, tx.city_name))
        affected_products.add(tx.product_id)
        if not dataset_id:
            dataset_id = tx.dataset_id

    # 2. Delete sales transactions
    deleted_tx_count = (
        db.query(SalesTransaction)
        .filter(
            (SalesTransaction.upload_job_id == upload_id) | (SalesTransaction.upload_id == upload_id)
        )
        .delete(synchronize_session=False)
    )

    # 3. Recalculate or delete DailyProductDemand for affected keys
    recalculated_demand_count = 0
    deleted_demand_count = 0
    for d_id, d_date, p_id, city in affected_keys:
        demand_row = (
            db.query(DailyProductDemand)
            .filter(
                DailyProductDemand.dataset_id == d_id,
                DailyProductDemand.date_ == d_date,
                DailyProductDemand.product_id == p_id,
                DailyProductDemand.city_name == city,
            )
            .first()
        )
        if demand_row:
            remaining_txs = (
                db.query(SalesTransaction)
                .filter(
                    SalesTransaction.dataset_id == d_id,
                    SalesTransaction.date_ == d_date,
                    SalesTransaction.product_id == p_id,
                    SalesTransaction.city_name == city,
                )
                .all()
            )
            if remaining_txs:
                total_qty = sum(float(tx.procured_quantity or 0.0) for tx in remaining_txs)
                total_rev = sum(float(tx.procured_quantity or 0.0) * float(tx.unit_selling_price or 0.0) for tx in remaining_txs)
                total_disc = sum(float(tx.total_discount_amount or 0.0) for tx in remaining_txs)
                demand_row.total_quantity = total_qty
                demand_row.total_sales_value = total_rev
                demand_row.total_discount_value = total_disc
                demand_row.order_count = len(set(tx.order_id for tx in remaining_txs if tx.order_id))
                demand_row.avg_unit_price = round(total_rev / total_qty, 2) if total_qty > 0 else 0.0
                recalculated_demand_count += 1
            else:
                db.delete(demand_row)
                deleted_demand_count += 1

    # 4. Invalidate downstream results
    if dataset_id:
        db.query(ForecastRun).filter(
            (ForecastRun.dataset_id == dataset_id) | (ForecastRun.source_upload_job_id == upload_id)
        ).update({"is_stale": True}, synchronize_session=False)

        if affected_products:
            db.query(InventoryRecommendation).filter(
                InventoryRecommendation.dataset_id == dataset_id,
                InventoryRecommendation.product_id.in_(affected_products)
            ).update({"is_stale": True}, synchronize_session=False)

        db.query(AnomalyAlert).filter(
            AnomalyAlert.dataset_id == dataset_id,
            AnomalyAlert.product_id.in_(affected_products)
        ).update({"is_stale": True}, synchronize_session=False)

    # 5. Delete upload job
    db.delete(upload_job)
    db.commit()

    # 6. Re-sync DuckDB Parquet if dataset exists
    if dataset_id:
        try:
            sync_dataset_to_duckdb(dataset_id, db)
        except Exception as d_err:
            print(f"DuckDB sync on upload delete notice: {d_err}")

    return {
        "status": "success",
        "deleted_job_id": upload_id,
        "deleted_transactions": deleted_tx_count,
        "deleted_sales_count": deleted_tx_count,
        "recalculated_demand_rows": recalculated_demand_count,
        "deleted_demand_rows": deleted_demand_count,
        "message": f"Upload job #{upload_id} successfully deleted and rolled back."
    }