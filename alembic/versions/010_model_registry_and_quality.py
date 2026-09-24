"""Prompt 5.7 & 5.9: Model Registry, Drift Records, and Data Quality Scorecards
Revision ID: 010_models_and_quality
Revises: 009_digests_and_nl_query
Create Date: 2026-09-21 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '010_models_and_quality'
down_revision = '009_digests_and_nl_query'

branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Update forecast_runs with champion fields
    if 'forecast_runs' in existing_tables:
        forecast_cols = [c['name'] for c in inspector.get_columns('forecast_runs')]
        if 'is_champion' not in forecast_cols:
            op.add_column('forecast_runs', sa.Column('is_champion', sa.Boolean(), nullable=False, server_default='false'))
            op.create_index('ix_forecast_runs_is_champion', 'forecast_runs', ['is_champion'])
        if 'promoted_at' not in forecast_cols:
            op.add_column('forecast_runs', sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True))
        if 'product_id' not in forecast_cols:
            op.add_column('forecast_runs', sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=True))
            op.create_index('ix_forecast_runs_product_id', 'forecast_runs', ['product_id'])

    # 2. model_drift_records table
    if 'model_drift_records' not in existing_tables:
        op.create_table(
            'model_drift_records',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('model_name', sa.String(100), nullable=False),
            sa.Column('baseline_wape', sa.Float(), nullable=False, default=0.0),
            sa.Column('rolling_wape', sa.Float(), nullable=False, default=0.0),
            sa.Column('wape_drift_pct', sa.Float(), nullable=False, default=0.0),
            sa.Column('psi_score', sa.Float(), nullable=False, default=0.0),
            sa.Column('kl_divergence', sa.Float(), nullable=False, default=0.0),
            sa.Column('drift_status', sa.String(50), nullable=False, default='STABLE'),
            sa.Column('retrain_flagged', sa.Boolean(), nullable=False, default=False),
            sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )
        op.create_index('idx_drift_dataset_product', 'model_drift_records', ['dataset_id', 'product_id'])

    # 3. data_quality_scorecards table
    if 'data_quality_scorecards' not in existing_tables:
        op.create_table(
            'data_quality_scorecards',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('upload_job_id', sa.Integer(), sa.ForeignKey('upload_jobs.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('composite_score', sa.Float(), nullable=False, default=100.0),
            sa.Column('quality_gate_passed', sa.Boolean(), nullable=False, default=True),
            sa.Column('completeness_score', sa.Float(), nullable=False, default=20.0),
            sa.Column('date_gap_score', sa.Float(), nullable=False, default=15.0),
            sa.Column('value_validity_score', sa.Float(), nullable=False, default=15.0),
            sa.Column('uniqueness_score', sa.Float(), nullable=False, default=10.0),
            sa.Column('outlier_score', sa.Float(), nullable=False, default=10.0),
            sa.Column('sku_mapping_score', sa.Float(), nullable=False, default=10.0),
            sa.Column('type_coercion_score', sa.Float(), nullable=False, default=5.0),
            sa.Column('zero_inflation_score', sa.Float(), nullable=False, default=5.0),
            sa.Column('history_depth_score', sa.Float(), nullable=False, default=5.0),
            sa.Column('freshness_score', sa.Float(), nullable=False, default=5.0),
            sa.Column('metrics_breakdown', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )
        op.create_index('idx_dqs_dataset_created', 'data_quality_scorecards', ['dataset_id', 'created_at'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'data_quality_scorecards' in existing_tables:
        op.drop_table('data_quality_scorecards')

    if 'model_drift_records' in existing_tables:
        op.drop_table('model_drift_records')

    if 'forecast_runs' in existing_tables:
        forecast_cols = [c['name'] for c in inspector.get_columns('forecast_runs')]
        if 'product_id' in forecast_cols:
            op.drop_column('forecast_runs', 'product_id')
        if 'promoted_at' in forecast_cols:
            op.drop_column('forecast_runs', 'promoted_at')
        if 'is_champion' in forecast_cols:
            op.drop_column('forecast_runs', 'is_champion')
