"""forecast run staleness and freshness metadata

Revision ID: 002_staleness
Revises: 001_scoping
Create Date: 2026-09-20 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_staleness'
down_revision = '001_scoping'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add staleness and freshness columns to forecast_runs
    op.add_column('forecast_runs', sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('forecast_runs', sa.Column('superseded_by', sa.Integer(), sa.ForeignKey('forecast_runs.id', ondelete='SET NULL'), nullable=True))
    op.add_column('forecast_runs', sa.Column('source_upload_job_id', sa.Integer(), sa.ForeignKey('upload_jobs.id', ondelete='SET NULL'), nullable=True))
    op.add_column('forecast_runs', sa.Column('data_date_max', sa.Date(), nullable=True))
    op.create_index('idx_forecast_runs_stale', 'forecast_runs', ['is_stale'])

    # 2. Add is_stale to inventory_recommendations
    op.add_column('inventory_recommendations', sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('idx_inv_rec_stale', 'inventory_recommendations', ['is_stale'])

    # 3. Add is_stale to anomalies
    op.add_column('anomalies', sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('idx_anomalies_stale', 'anomalies', ['is_stale'])


def downgrade() -> None:
    op.drop_index('idx_anomalies_stale', table_name='anomalies')
    op.drop_column('anomalies', 'is_stale')

    op.drop_index('idx_inv_rec_stale', table_name='inventory_recommendations')
    op.drop_column('inventory_recommendations', 'is_stale')

    op.drop_index('idx_forecast_runs_stale', table_name='forecast_runs')
    op.drop_column('forecast_runs', 'data_date_max')
    op.drop_column('forecast_runs', 'source_upload_job_id')
    op.drop_column('forecast_runs', 'superseded_by')
    op.drop_column('forecast_runs', 'is_stale')
