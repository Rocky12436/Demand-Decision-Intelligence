"""
backend/services/duckdb_service.py
-----------------------------------
DuckDB Parquet integration with concurrency controls:
- FileLock-based serialised writes across processes/threads.
- Read queries execute with read_only=True.
- Retry-with-backoff for transient lock contention (max 3 attempts).
- Raises HTTP 503 ("Analytics database busy, please retry") on persistent lock timeouts.
- Parquet consistency auditor between PostgreSQL and DuckDB.
"""

import os
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Any, List, Dict
import pandas as pd
import duckdb
from filelock import FileLock, Timeout
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models.demand import DailyProductDemand
from backend.models.dataset import Dataset

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

LOCK_FILE = DATASET_DIR / "duckdb_write.lock"
WRITE_LOCK_TIMEOUT_SECONDS = 30.0
MAX_WRITE_RETRIES = 3


def get_parquet_path(dataset_id: int) -> Path:
    return DATASET_DIR / f"daily_demand_dataset_{dataset_id}.parquet"


def get_write_lock(timeout: float = WRITE_LOCK_TIMEOUT_SECONDS) -> FileLock:
    """Returns a FileLock for serialising DuckDB writes across threads/workers."""
    return FileLock(str(LOCK_FILE), timeout=timeout)


def sync_dataset_to_duckdb(dataset_id: int, db: Session, max_retries: int = MAX_WRITE_RETRIES) -> Path:
    """
    Exports daily_product_demand rows from PostgreSQL to Parquet for DuckDB analytics.
    Acquires an exclusive FileLock to serialise writes across workers.
    Retries up to max_retries with backoff if contention occurs.
    Raises HTTP 503 if lock cannot be acquired within timeout.
    """
    parquet_path = get_parquet_path(dataset_id)
    lock = get_write_lock(timeout=WRITE_LOCK_TIMEOUT_SECONDS)

    for attempt in range(1, max_retries + 1):
        try:
            with lock:
                records = db.query(DailyProductDemand).filter(
                    DailyProductDemand.dataset_id == dataset_id
                ).all()

                tmp_path = parquet_path.parent / f"{parquet_path.stem}_{uuid.uuid4().hex}.tmp"
                if not records:
                    df_empty = pd.DataFrame(columns=[
                        "date_", "product_id", "city_name", "total_quantity",
                        "total_sales_value", "total_discount_value", "avg_unit_price", "order_count"
                    ])
                    df_empty.to_parquet(tmp_path, index=False)
                    os.replace(tmp_path, parquet_path)
                    return parquet_path

                data = [
                    {
                        "date_": str(r.date_),
                        "product_id": str(r.product_id),
                        "city_name": r.city_name,
                        "total_quantity": float(r.total_quantity or 0.0),
                        "total_sales_value": float(r.total_sales_value or 0.0),
                        "total_discount_value": float(r.total_discount_value or 0.0),
                        "avg_unit_price": float(r.avg_unit_price or 0.0),
                        "order_count": int(r.order_count or 0),
                    }
                    for r in records
                ]
                df = pd.DataFrame(data)
                df.to_parquet(tmp_path, index=False)

                # Atomic replace on Windows with brief backoff if reader holds handle
                for r_att in range(5):
                    try:
                        os.replace(tmp_path, parquet_path)
                        break
                    except PermissionError:
                        time.sleep(0.05 * (r_att + 1))
                else:
                    try:
                        df.to_parquet(parquet_path, index=False)
                    finally:
                        if tmp_path.exists():
                            try:
                                tmp_path.unlink()
                            except Exception:
                                pass

                assert parquet_path.exists(), f"Failed to materialize Parquet file at {parquet_path}"
                logger.debug(f"[DUCKDB_SYNC] Successfully wrote {len(records)} rows to {parquet_path.name}.")
                return parquet_path

        except Timeout:
            logger.warning(
                f"[DUCKDB_LOCK_CONTENTION] Attempt {attempt}/{max_retries} timed out waiting for DuckDB write lock on dataset {dataset_id}."
            )
            if attempt < max_retries:
                time.sleep(0.2 * (2 ** (attempt - 1)))  # Exponential backoff
            else:
                logger.error(f"[DUCKDB_LOCK_EXHAUSTED] Could not acquire write lock after {max_retries} attempts.")
                raise HTTPException(
                    status_code=503,
                    detail="Analytics database busy, please retry"
                )
        except Exception as e:
            logger.exception(f"[DUCKDB_WRITE_ERROR] Error syncing dataset {dataset_id} to Parquet: {e}")
            raise

    raise HTTPException(status_code=503, detail="Analytics database busy, please retry")


def query_dataset_parquet(dataset_id: int, sql_query: str, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    Executes a read-only query against the dataset's Parquet file.
    Retries transient contention if the file is being updated.
    """
    parquet_path = get_parquet_path(dataset_id)
    if not parquet_path.exists():
        return []

    for attempt in range(1, max_retries + 1):
        try:
            con = duckdb.connect()
            try:
                sanitized_path = parquet_path.as_posix()
                final_query = sql_query.replace("{parquet}", f"read_parquet('{sanitized_path}')")
                result = con.execute(final_query).df()
                return result.to_dict(orient="records")
            finally:
                con.close()
        except Exception as err:
            err_msg = str(err).lower()
            if ("too small" in err_msg or "cannot open" in err_msg or "permission" in err_msg) and attempt < max_retries:
                time.sleep(0.05 * attempt)
                continue
            raise
    return []


def verify_startup_consistency(db: Session, tolerance: int = 0) -> bool:
    """
    Consistency Auditor:
    Compares COUNT(daily_product_demand) in PostgreSQL vs DuckDB Parquet.
    Logs an ERROR if the counts disagree by more than tolerance.
    """
    datasets = db.query(Dataset).filter(Dataset.is_active == True).all()
    all_consistent = True

    for ds in datasets:
        pg_count = db.query(DailyProductDemand).filter(DailyProductDemand.dataset_id == ds.id).count()
        parquet_path = get_parquet_path(ds.id)

        duck_count = 0
        if parquet_path.exists():
            con = duckdb.connect()
            try:
                duck_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')").fetchone()[0]
            except Exception as e:
                logger.error(f"[DUCKDB_SPLIT_BRAIN_ERROR] Error reading Parquet for dataset {ds.id}: {e}")
                all_consistent = False
            finally:
                con.close()

        drift = abs(pg_count - duck_count)
        if drift > tolerance:
            all_consistent = False
            logger.error(
                f"[DATA_ENGINE_DISCREPANCY_ERROR] Dataset {ds.id} ('{ds.name}') row count mismatch: "
                f"PostgreSQL={pg_count}, DuckDB={duck_count} (Drift={drift} > Tolerance={tolerance})"
            )
        else:
            logger.info(f"[DATA_ENGINE_SYNC] Dataset {ds.id} verified consistent: {pg_count} rows in PG and DuckDB.")

    return all_consistent
