import os
import logging
from contextvars import ContextVar
from typing import Optional
from sqlalchemy import event
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.db.session import engine
from backend.models.dataset import Dataset
from backend.models.user import User

logger = logging.getLogger(__name__)

# Context variable to optionally allow unscoped queries for migrations/admin tasks
bypass_scoping_check: ContextVar[bool] = ContextVar("bypass_scoping_check", default=False)

SCOPED_TABLE_NAMES = {
    "daily_product_demand",
    "forecast_runs",
    "forecasts",
    "inventory_recommendations",
    "anomalies",
    "sales",
}


def resolve_dataset(
    db: Session,
    user: Optional[User] = None,
    dataset_id: Optional[int] = None
) -> Dataset:
    """
    Resolves the dataset to operate on:
    1. Explicitly requested dataset_id (if provided).
    2. User's most recent active dataset (if user provided).
    3. Active 'Demo Data' / seed dataset as fallback.
    """
    if dataset_id is not None:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.is_active == True
        ).first()
        if not dataset:
            raise HTTPException(status_code=404, detail=f"Dataset with id {dataset_id} not found or inactive.")
        return dataset

    if user is not None and getattr(user, "id", None) is not None:
        user_dataset = db.query(Dataset).filter(
            Dataset.user_id == user.id,
            Dataset.is_active == True
        ).order_by(Dataset.id.desc()).first()
        if user_dataset:
            return user_dataset

    # Fallback to seed/Demo Data
    demo_dataset = db.query(Dataset).filter(
        Dataset.name == "Demo Data",
        Dataset.is_active == True
    ).first()

    if not demo_dataset:
        demo_dataset = db.query(Dataset).filter(
            Dataset.source == "seed",
            Dataset.is_active == True
        ).first()

    if not demo_dataset:
        # Create Demo Data if missing
        demo_dataset = Dataset(
            name="Demo Data",
            source="seed",
            is_active=True,
            row_count=0
        )
        db.add(demo_dataset)
        db.commit()
        db.refresh(demo_dataset)

    return demo_dataset


def install_query_scoping_guard():
    """
    SQLAlchemy event listener guard that ensures any SELECT query
    touching scoped tables includes a dataset_id filter.
    Fails loudly in dev/test, logs alert in production.
    """
    @event.listens_for(engine, "before_cursor_execute", retval=False)
    def check_query_dataset_scoping(conn, cursor, statement, parameters, context, executemany):
        if bypass_scoping_check.get():
            return

        stmt_str = str(statement).strip()
        stmt_upper = stmt_str.upper()

        if not stmt_upper.startswith("SELECT"):
            return

        stmt_lower = stmt_str.lower()
        # Skip introspection, alembic, and internal sqlite/postgres metadata
        if any(meta in stmt_lower for meta in ("information_schema", "pg_catalog", "alembic_version", "sqlite_master")):
            return

        for tbl in SCOPED_TABLE_NAMES:
            if f"from {tbl}" in stmt_lower or f"join {tbl}" in stmt_lower:
                if "dataset_id" not in stmt_lower:
                    err_msg = (
                        f"[DATASET SCOPING GUARD VIOLATION] Query against scoped table '{tbl}' "
                        f"lacks a dataset_id filter!\nSQL: {statement}"
                    )
                    env = os.getenv("APP_ENV", "development").lower()
                    if env in ("development", "dev", "test"):
                        raise RuntimeError(err_msg)
                    else:
                        logger.error(err_msg)


# Initialize guard
install_query_scoping_guard()
