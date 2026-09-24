"""
backend/db/session.py
---------------------
Database session management with Read-Only Degraded Mode (Prompt 3.4).
- Primary engine: PostgreSQL
- Fallback engine: SQLite cached replica
- When PostgreSQL is unreachable, sets IS_DEGRADED_MODE = True.
- Mutative operations are blocked with HTTP 503 in degraded mode via enforce_writable_db.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi import HTTPException, status

from backend.core.config import settings

logger = logging.getLogger(__name__)

# State tracking for degraded mode
IS_DEGRADED_MODE: bool = False
DEGRADED_SINCE: Optional[datetime] = None

# Primary PostgreSQL Engine
primary_engine = None
try:
    primary_engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False
    )
except Exception as e:
    logger.warning(f"Could not initialize PostgreSQL engine: {e}")

# Fallback SQLite Engine for read-only serving
FALLBACK_SQLITE_URL = "sqlite:///./demand_decision_fallback.db"
fallback_engine = create_engine(
    FALLBACK_SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

# Active engine reference
engine = primary_engine if primary_engine else fallback_engine

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

FallbackSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=fallback_engine
)

Base = declarative_base()


def check_db_health(timeout_seconds: float = 2.0) -> Dict[str, Any]:
    """
    Actively probes PostgreSQL.
    If PostgreSQL fails or times out, switches IS_DEGRADED_MODE to True.
    """
    global IS_DEGRADED_MODE, DEGRADED_SINCE, engine, SessionLocal

    if primary_engine is None:
        IS_DEGRADED_MODE = True
        if not DEGRADED_SINCE:
            DEGRADED_SINCE = datetime.now(timezone.utc)
        return {
            "postgres": "disconnected",
            "is_degraded": True,
            "serving_engine": "sqlite_cached",
            "degraded_since": DEGRADED_SINCE.isoformat(),
        }

    try:
        t0 = time.time()
        with primary_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.time() - t0) * 1000, 2)

        # Recovered
        if IS_DEGRADED_MODE:
            logger.info("[DB_RECOVERY] PostgreSQL connection restored; exiting degraded mode.")
        IS_DEGRADED_MODE = False
        DEGRADED_SINCE = None
        return {
            "postgres": "connected",
            "is_degraded": False,
            "serving_engine": "postgresql",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        if not IS_DEGRADED_MODE:
            logger.error(f"[DEGRADED_MODE_TRIGGER] PostgreSQL unreachable ({exc}); entering Read-Only Degraded Mode.")
            DEGRADED_SINCE = datetime.now(timezone.utc)
        IS_DEGRADED_MODE = True
        return {
            "postgres": "disconnected",
            "is_degraded": True,
            "serving_engine": "sqlite_cached",
            "degraded_since": DEGRADED_SINCE.isoformat() if DEGRADED_SINCE else None,
            "error": str(exc),
        }


def get_db():
    """
    Yields database session. If in degraded mode, yields from fallback SQLite engine.
    """
    global IS_DEGRADED_MODE
    if IS_DEGRADED_MODE:
        db = FallbackSessionLocal()
    else:
        db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def enforce_writable_db():
    """
    FastAPI dependency for mutative routes (uploads, recompute, deletes).
    Blocks writes with HTTP 503 if PostgreSQL is down and system is in degraded mode.
    """
    if IS_DEGRADED_MODE:
        since_str = DEGRADED_SINCE.isoformat() if DEGRADED_SINCE else "recently"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Service in read-only degraded mode. PostgreSQL is currently unreachable "
                f"(degraded since {since_str}). Mutations are blocked until database recovery."
            ),
        )
