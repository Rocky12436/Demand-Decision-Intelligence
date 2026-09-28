"""012_forecast_accuracy_and_traceability

Adds fields required for:
- Tracing model_requested vs model_used (fixing Bug B1)
- Skipped model recording with plain-language reason
- Idempotency via data_version_hash (fixing Bug B2)
- Bias and improvement_vs_naive_pct on evaluations
- Async job tracking for forecast runs

Revision ID: 012
Revises: 011
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "012_forecast_traceability"
down_revision = "011_active_dataset"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # -----------------------------------------------------------------------
    # forecast_runs: add model_requested, skip_reason, data_version_hash
    # -----------------------------------------------------------------------
    if "forecast_runs" in existing_tables:
        cols = {c["name"] for c in inspector.get_columns("forecast_runs")}
        with op.batch_alter_table("forecast_runs", schema=None) as batch_op:
            if "model_requested" not in cols:
                batch_op.add_column(sa.Column("model_requested", sa.String(100), nullable=True))
            if "skip_reason" not in cols:
                batch_op.add_column(sa.Column("skip_reason", sa.Text(), nullable=True))
            if "data_version_hash" not in cols:
                batch_op.add_column(sa.Column("data_version_hash", sa.String(64), nullable=True))
            if "history_obs_count" not in cols:
                batch_op.add_column(sa.Column("history_obs_count", sa.Integer(), nullable=True))
            if "job_id" not in cols:
                batch_op.add_column(sa.Column("job_id", sa.String(64), nullable=True))

    # -----------------------------------------------------------------------
    # forecast_evaluations: add bias and improvement_vs_naive_pct
    # -----------------------------------------------------------------------
    if "forecast_evaluations" in existing_tables:
        eval_cols = {c["name"] for c in inspector.get_columns("forecast_evaluations")}
        with op.batch_alter_table("forecast_evaluations", schema=None) as batch_op:
            if "bias" not in eval_cols:
                batch_op.add_column(sa.Column("bias", sa.Float(), nullable=True))
            if "improvement_vs_naive_pct" not in eval_cols:
                batch_op.add_column(sa.Column("improvement_vs_naive_pct", sa.Float(), nullable=True))
            if "fold_index" not in eval_cols:
                batch_op.add_column(sa.Column("fold_index", sa.Integer(), nullable=True))
            if "pinball_loss" not in eval_cols:
                batch_op.add_column(sa.Column("pinball_loss", sa.Float(), nullable=True))
            if "coverage_50" not in eval_cols:
                batch_op.add_column(sa.Column("coverage_50", sa.Float(), nullable=True))
            if "coverage_90" not in eval_cols:
                batch_op.add_column(sa.Column("coverage_90", sa.Float(), nullable=True))

    # -----------------------------------------------------------------------
    # forecast_jobs: lightweight async job tracking table
    # -----------------------------------------------------------------------
    if "forecast_jobs" not in existing_tables:
        op.create_table(
            "forecast_jobs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
            sa.Column("dataset_id", sa.Integer(), nullable=True),
            sa.Column("product_ids", sa.Text(), nullable=True),   # JSON list
            sa.Column("models", sa.Text(), nullable=True),         # JSON list
            sa.Column("horizon_days", sa.Integer(), nullable=True),
            sa.Column("result_summary", sa.Text(), nullable=True), # JSON
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.drop_table("forecast_jobs")

    with op.batch_alter_table("forecast_evaluations", schema=None) as batch_op:
        batch_op.drop_column("bias")
        batch_op.drop_column("improvement_vs_naive_pct")
        batch_op.drop_column("fold_index")
        batch_op.drop_column("pinball_loss")
        batch_op.drop_column("coverage_50")
        batch_op.drop_column("coverage_90")

    with op.batch_alter_table("forecast_runs", schema=None) as batch_op:
        batch_op.drop_column("model_requested")
        batch_op.drop_column("skip_reason")
        batch_op.drop_column("data_version_hash")
        batch_op.drop_column("history_obs_count")
        batch_op.drop_column("job_id")
