# Data Engine Contract: PostgreSQL & DuckDB

This document establishes the architectural read/write boundary between **PostgreSQL** and **DuckDB** in the Demand & Decision Intelligence System.

---

## 1. System of Record vs Derived Replica

| Storage Engine | Role | Guarantees | Assigned Tables / Entities |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | **OLTP (System of Record)** | ACID transactional integrity, multi-tenant row-level security, constraints, sequences, foreign keys | `users`, `roles`, `datasets`, `upload_jobs`, `validation_results`, `products`, `sku_mappings`, `inventory_recommendations`, `inventory`, `forecast_runs`, `forecasts`, `forecast_evaluations`, `anomalies`, `chat_sessions`, `chat_messages`, `audit_logs` |
| **DuckDB** | **OLAP (Derived Replica)** | Vectorized in-process analytical execution, wide window functions, calendar grids, time-series feature engineering | Rebuilt from PostgreSQL: `sales_transactions`, `daily_product_demand`, rolling aggregations, calendar matrices |

---

## 2. Invariant Rules & Guarantees

1. **Single Source of Truth**:
   - All client writes (uploads, SKU resolutions, user decisions, configuration updates) **MUST** be committed to PostgreSQL first.
   - DuckDB **NEVER** acts as the primary authority for any transaction.
2. **Explicit Synchronization**:
   - When new sales transactions or daily demand aggregations are committed to PostgreSQL, the derived Parquet representation (`dataset/daily_demand_dataset_{dataset_id}.parquet`) is materialized.
   - **Timestamp Assertion**: No read from Parquet may occur if the Parquet file's modification timestamp is older than the newest `DailyProductDemand.created_at` or `date_` in PostgreSQL for that scope.
3. **Startup Consistency Check**:
   - On application startup, a consistency check verifies that the recorded row count in PostgreSQL matches the row count in DuckDB within a zero-tolerance threshold. Any drift logs an `ERROR`.
4. **Disaster Recovery / Escape Hatch**:
   - If derived OLAP data drifts or is corrupted, `python -m backend.cli.rebuild_olap --dataset-id N` completely drops and reconstructs the DuckDB Parquet replica directly from PostgreSQL.
