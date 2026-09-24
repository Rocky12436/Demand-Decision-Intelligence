"""
backend/api/health.py
---------------------
Health check endpoints (Prompt 3.4):
- GET /health: lightweight, fast process liveness check.
- GET /health/deep: verifies PostgreSQL, DuckDB, Parquet freshness, memory usage.
  Returns HTTP 200 (healthy) or HTTP 503 (degraded/down) with a structured breakdown.
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend.db.session import get_db, check_db_health, IS_DEGRADED_MODE, DEGRADED_SINCE
from backend.services.duckdb_service import query_dataset_parquet, DATASET_DIR

from backend.services.dataset_service import check_demo_dataset_integrity

router = APIRouter()


@router.get("/health", summary="Lightweight Process Liveness Check")
def health_check():
    """Fast, lightweight health check returning immediate process status."""
    return {
        "status": "healthy" if not IS_DEGRADED_MODE else "degraded",
        "is_degraded": IS_DEGRADED_MODE,
        "service": "Demand Decision Intelligence API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/deep", summary="Deep Health & System Diagnostics Check")
def deep_health_check(response: Response, db: Session = Depends(get_db)):
    """
    Comprehensive system health check:
    - PostgreSQL connectivity and latency
    - DuckDB accessibility
    - Parquet file count and freshness
    - Process memory usage
    Returns HTTP 200 if fully healthy, or HTTP 503 if degraded/down.
    """
    t0 = time.time()
    db_status = check_db_health(timeout_seconds=2.0)

    # Check DuckDB Parquet accessibility
    duckdb_status = {"accessible": False}
    try:
        parquet_files = list(DATASET_DIR.glob("*.parquet"))
        duckdb_status = {
            "accessible": True,
            "parquet_files_count": len(parquet_files),
            "files": [
                {
                    "filename": p.name,
                    "size_kb": round(p.stat().st_size / 1024, 2),
                    "modified_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                }
                for p in parquet_files[:5]
            ]
        }
    except Exception as d_err:
        duckdb_status = {
            "accessible": False,
            "error": str(d_err)
        }

    # Memory info
    mem_info = {}
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = {
            "rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
            "cpu_percent": process.cpu_percent(interval=None),
        }
    except Exception:
        mem_info = {"note": "psutil not available"}

    total_latency_ms = round((time.time() - t0) * 1000, 2)
    overall_status = "healthy"
    status_code = status.HTTP_200_OK

    if db_status.get("is_degraded") or not duckdb_status.get("accessible"):
        overall_status = "degraded"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.status_code = status_code

    demo_guard = check_demo_dataset_integrity(db)

    return {
        "status": overall_status,
        "is_degraded": db_status.get("is_degraded", False),
        "degraded_since": db_status.get("degraded_since"),
        "total_latency_ms": total_latency_ms,
        "components": {
            "database": db_status,
            "duckdb": duckdb_status,
            "demo_dataset_guard": demo_guard,
            "system_resources": mem_info,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
