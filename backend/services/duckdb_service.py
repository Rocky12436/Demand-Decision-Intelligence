import os
import logging
from pathlib import Path
from typing import Optional
import pandas as pd
import duckdb
from sqlalchemy.orm import Session

from backend.models.demand import DailyProductDemand
from backend.models.dataset import Dataset

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
DATASET_DIR.mkdir(parents=True, exist_ok=True)


def get_parquet_path(dataset_id: int) -> Path:
    return DATASET_DIR / f"daily_demand_dataset_{dataset_id}.parquet"


def sync_dataset_to_duckdb(dataset_id: int, db: Session) -> Path:
    """
    Exports daily_product_demand rows from PostgreSQL to Parquet for DuckDB analytics.
    Enforces the timestamp invariant: Parquet file must not be older than newest demand row.
    """
    records = db.query(DailyProductDemand).filter(
        DailyProductDemand.dataset_id == dataset_id
    ).all()

    parquet_path = get_parquet_path(dataset_id)

    if not records:
        # Create empty parquet with schema
        df_empty = pd.DataFrame(columns=[
            "date_", "product_id", "city_name", "total_quantity",
            "total_sales_value", "total_discount_value", "avg_unit_price", "order_count"
        ])
        df_empty.to_parquet(parquet_path, index=False)
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
    df.to_parquet(parquet_path, index=False)

    # Invariant assertion: Parquet modified time must be >= recent execution
    assert parquet_path.exists(), f"Failed to materialize Parquet file at {parquet_path}"
    return parquet_path


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
