"""
Clean Slate Reset Script
Resets PostgreSQL database to a true 0-state:
- Empties all demand, sales, inventory, forecast, anomalies, and upload records
- Leaves 1 clean Default Workspace dataset with row_count=0
- Resets all users' active_dataset_id
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from backend.db.session import SessionLocal, engine
from backend.models.dataset import Dataset
from backend.models.user import User

def reset_to_clean_slate():
    db = SessionLocal()
    try:
        print("Clearing all transactional and dataset-specific records...")
        tables_to_truncate = [
            "recommendation_events",
            "recommendations",
            "purchase_order_lines",
            "purchase_orders",
            "goods_receipt_lines",
            "goods_receipts",
            "transfer_order_lines",
            "transfer_orders",
            "transfer_lanes",
            "dead_stock_records",
            "product_classifications",
            "model_drift_records",
            "data_quality_scorecards",
            "validation_results",
            "upload_jobs",
            "sku_mappings",
            "anomalies",
            "alerts",
            "forecast_evaluations",
            "forecasts",
            "forecast_runs",
            "inventory_recommendations",
            "inventory",
            "sales",
            "daily_product_demand",
            "chat_messages",
            "chat_sessions",
            "weekly_digests",
            "datasets",
        ]
        
        with engine.begin() as conn:
            for tbl in tables_to_truncate:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {tbl} CASCADE;"))
                except Exception as e:
                    print(f"Notice truncating {tbl}: {e}")

        # Create one clean default dataset with 0 rows
        clean_ds = Dataset(
            name="Default Workspace",
            source="upload",
            is_active=True,
            is_default_upload_target=True,
            row_count=0,
            status="active"
        )
        db.add(clean_ds)
        db.commit()
        db.refresh(clean_ds)
        print(f"Created clean dataset ID {clean_ds.id}: '{clean_ds.name}' (0 rows)")

        # Set user active dataset to the clean one
        users = db.query(User).all()
        for u in users:
            u.active_dataset_id = clean_ds.id
        db.commit()
        print(f"Updated {len(users)} users to active_dataset_id={clean_ds.id}")

        print("SUCCESS: System successfully reset to clean zero-state!")
    finally:
        db.close()

if __name__ == "__main__":
    reset_to_clean_slate()
