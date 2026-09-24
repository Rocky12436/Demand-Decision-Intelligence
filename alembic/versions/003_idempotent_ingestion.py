"""idempotent ingestion, file hash, and conflict mode

Revision ID: 003_idempotent
Revises: 002_staleness
Create Date: 2026-09-20 22:25:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_idempotent'
down_revision = '002_staleness'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add dataset_id, file_hash, conflict_mode to upload_jobs
    op.add_column('upload_jobs', sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True))
    op.add_column('upload_jobs', sa.Column('file_hash', sa.String(64), nullable=True))
    op.add_column('upload_jobs', sa.Column('conflict_mode', sa.String(20), nullable=False, server_default='replace'))
    op.create_index('idx_upload_jobs_file_hash', 'upload_jobs', ['file_hash'])
    op.create_index('idx_upload_jobs_dataset_id', 'upload_jobs', ['dataset_id'])

    # 2. Check and add unique constraint on daily_product_demand
    try:
        op.create_unique_constraint(
            'uq_daily_demand_dataset_date_product_city',
            'daily_product_demand',
            ['dataset_id', 'date_', 'product_id', 'city_name']
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_constraint('uq_daily_demand_dataset_date_product_city', 'daily_product_demand', type_='unique')
    except Exception:
        pass

    op.drop_index('idx_upload_jobs_dataset_id', table_name='upload_jobs')
    op.drop_index('idx_upload_jobs_file_hash', table_name='upload_jobs')
    op.drop_column('upload_jobs', 'conflict_mode')
    op.drop_column('upload_jobs', 'file_hash')
    op.drop_column('upload_jobs', 'dataset_id')
