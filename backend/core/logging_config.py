"""
backend/core/logging_config.py
------------------------------
Structured JSON logging via structlog with request_id, user_id, dataset_id context.
Prometheus metrics instrumenting latency, ingestion, forecasts, and DuckDB queries.
"""

import sys
import logging
import contextvars
from datetime import datetime, timezone
import structlog
from prometheus_client import Counter, Histogram, Gauge

# Context variables for tracing across request lifecycles
request_id_ctx = contextvars.ContextVar("request_id", default="")
user_id_ctx = contextvars.ContextVar("user_id", default="")
dataset_id_ctx = contextvars.ContextVar("dataset_id", default="")

# ----------------------------------------------------
# Prometheus Metrics (Prompt 3.5)
# ----------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests",
    ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

INGESTION_DURATION = Histogram(
    "ingestion_duration_seconds",
    "Time taken to ingest and validate uploaded sales files",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
)

INGESTION_QUEUE_DEPTH = Gauge(
    "ingestion_queue_depth",
    "Number of pending or processing ingestion jobs in the queue"
)

FORECAST_DURATION = Histogram(
    "forecast_generation_duration_seconds",
    "Time taken to generate forecasts by model",
    ["model_name"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0)
)

DUCKDB_QUERY_DURATION = Histogram(
    "duckdb_query_latency_seconds",
    "Latency of DuckDB Parquet analytics queries",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)


def add_request_context(logger, method_name, event_dict):
    """Injects active request_id, user_id, dataset_id into all log lines."""
    req_id = request_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id

    u_id = user_id_ctx.get()
    if u_id:
        event_dict["user_id"] = u_id

    ds_id = dataset_id_ctx.get()
    if ds_id:
        event_dict["dataset_id"] = ds_id

    if "timestamp" not in event_dict:
        event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()

    return event_dict


def setup_logging():
    """Configures structured JSON logging globally."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_request_context,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
