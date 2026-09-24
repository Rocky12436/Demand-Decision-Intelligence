import argparse
import sys
from backend.db.session import SessionLocal
from backend.models.dataset import Dataset
from backend.services.duckdb_service import sync_dataset_to_duckdb, verify_startup_consistency


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild DuckDB OLAP derived Parquet tables from PostgreSQL system of record."
    )
    parser.add_argument(
        "--dataset-id",
        type=int,
        required=False,
        default=None,
        help="Specific Dataset ID to rebuild. If omitted, all active datasets are rebuilt."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.dataset_id is not None:
            dataset = db.query(Dataset).filter(Dataset.id == args.dataset_id).first()
            if not dataset:
                print(f"Error: Dataset {args.dataset_id} not found.")
                sys.exit(1)
            target_ids = [args.dataset_id]
        else:
            datasets = db.query(Dataset).filter(Dataset.is_active == True).all()
            target_ids = [d.id for d in datasets]

        print(f"Rebuilding DuckDB OLAP replicas for dataset(s): {target_ids}...")
        for ds_id in target_ids:
            p = sync_dataset_to_duckdb(ds_id, db)
            print(f"  -> Dataset {ds_id}: Materialized {p}")

        consistent = verify_startup_consistency(db)
        if consistent:
            print("Successfully verified: DuckDB replicas match PostgreSQL system of record.")
        else:
            print("Warning: Minor discrepancy observed after rebuild.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
