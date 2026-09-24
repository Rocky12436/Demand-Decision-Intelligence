from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    model_name = Column(String(100), nullable=False, index=True)  # Prophet, MovingAverage_7D, Naive
    horizon_days = Column(Integer, nullable=False, default=14)  # 7, 14, 30
    status = Column(String(50), nullable=False, default="RUNNING", index=True)  # RUNNING, COMPLETED, FAILED
    is_stale = Column(Boolean, nullable=False, default=False, index=True)
    superseded_by = Column(Integer, ForeignKey("forecast_runs.id", ondelete="SET NULL"), nullable=True)
    source_upload_job_id = Column(Integer, ForeignKey("upload_jobs.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=True, index=True)
    is_champion = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    data_date_max = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    metrics_summary = Column(Text, nullable=True)  # JSON summary of metrics
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    dataset = relationship("Dataset", back_populates="forecast_runs")
    forecast_items = relationship("ForecastItem", back_populates="run", cascade="all, delete-orphan")
    evaluations = relationship("ForecastEvaluation", back_populates="run", cascade="all, delete-orphan")
    source_upload_job = relationship("UploadJob", backref="forecast_runs")

class ForecastItem(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL", index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    predicted_demand = Column(Float, nullable=False)
    lower_bound = Column(Float, nullable=True)
    upper_bound = Column(Float, nullable=True)
    quantiles = Column(JSON, nullable=True)  # {"p05": ..., "p25": ..., "p50": ..., "p75": ..., "p90": ..., "p95": ..., "p99": ...}
    model_name = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("ForecastRun", back_populates="forecast_items")
    product = relationship("Product", back_populates="forecast_items")

    __table_args__ = (
        UniqueConstraint("run_id", "product_id", "city_name", "forecast_date", name="uq_forecast_run_product_city_date"),
        Index("idx_forecast_product_date", "product_id", "forecast_date"),
        Index("idx_forecast_dataset_id", "dataset_id"),
    )

class ForecastEvaluation(Base):
    __tablename__ = "forecast_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    city_name = Column(String(100), nullable=False, default="ALL")
    model_name = Column(String(100), nullable=False)
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)
    wape = Column(Float, nullable=True)
    evaluation_date = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("ForecastRun", back_populates="evaluations")


class ModelDriftRecord(Base):
    __tablename__ = "model_drift_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    baseline_wape = Column(Float, nullable=False, default=0.0)
    rolling_wape = Column(Float, nullable=False, default=0.0)
    wape_drift_pct = Column(Float, nullable=False, default=0.0)  # relative % change in WAPE
    psi_score = Column(Float, nullable=False, default=0.0)  # Population Stability Index
    kl_divergence = Column(Float, nullable=False, default=0.0)
    drift_status = Column(String(50), nullable=False, default="STABLE")  # STABLE, WARNING, DRIFT_DETECTED
    retrain_flagged = Column(Boolean, nullable=False, default=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_drift_dataset_product", "dataset_id", "product_id"),
    )
