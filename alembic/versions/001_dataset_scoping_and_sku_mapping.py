"""dataset scoping and sku mapping

Revision ID: 001_scoping
Revises: 
Create Date: 2026-09-20 16:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select


# revision identifiers, used by Alembic.
revision = '001_scoping'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create datasets table
    op.create_table(
        'datasets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False, server_default='upload'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('date_min', sa.Date(), nullable=True),
        sa.Column('date_max', sa.Date(), nullable=True),
    )
    op.create_index('idx_datasets_user_active', 'datasets', ['user_id', 'is_active'])

    # 2. Backfill initial 'Demo Data' dataset
    datasets_table = table(
        'datasets',
        column('id', sa.Integer),
        column('name', sa.String),
        column('source', sa.String),
        column('is_active', sa.Boolean),
        column('row_count', sa.Integer),
    )
    op.execute(
        datasets_table.insert().values(
            name='Demo Data',
            source='seed',
            is_active=True,
            row_count=0
        )
    )

    # 3. Add is_provisional and source_upload_job_id to products
    op.add_column('products', sa.Column('is_provisional', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('products', sa.Column('source_upload_job_id', sa.Integer(), sa.ForeignKey('upload_jobs.id', ondelete='SET NULL'), nullable=True))

    # 4. Create sku_mappings table
    op.create_table(
        'sku_mappings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=True),
        sa.Column('external_sku', sa.String(length=100), nullable=False),
        sa.Column('internal_product_id', sa.String(length=100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('mapping_method', sa.String(length=50), nullable=False),  # exact, fuzzy, manual
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_sku_mappings_external_sku', 'sku_mappings', ['external_sku'])
    op.create_index('idx_sku_mappings_dataset_sku', 'sku_mappings', ['dataset_id', 'external_sku'])

    # Helper connection to get demo_id
    connection = op.get_bind()
    demo_id = connection.execute(sa.text("SELECT id FROM datasets WHERE name = 'Demo Data' LIMIT 1")).scalar() or 1

    # 5. Add dataset_id to scoped tables with backfill default
    scoped_tables = [
        'sales',
        'daily_product_demand',
        'forecast_runs',
        'forecasts',
        'inventory_recommendations',
        'anomalies'
    ]

    for tbl in scoped_tables:
        op.add_column(tbl, sa.Column('dataset_id', sa.Integer(), nullable=True))
        # Backfill existing rows to Demo Data
        op.execute(f"UPDATE {tbl} SET dataset_id = {demo_id} WHERE dataset_id IS NULL")
        # Alter to NOT NULL and add foreign key
        op.alter_column(tbl, 'dataset_id', nullable=False)
        op.create_foreign_key(f'{tbl}_dataset_id_fkey', tbl, 'datasets', ['dataset_id'], ['id'], ondelete='CASCADE')
        op.create_index(f'idx_{tbl}_dataset_id', tbl, ['dataset_id'])

    # 6. Add upload_job_id to sales and daily_product_demand
    op.add_column('daily_product_demand', sa.Column('upload_job_id', sa.Integer(), sa.ForeignKey('upload_jobs.id', ondelete='SET NULL'), nullable=True))
    op.create_index('idx_daily_demand_upload_job_id', 'daily_product_demand', ['upload_job_id'])

    op.add_column('sales', sa.Column('upload_job_id', sa.Integer(), sa.ForeignKey('upload_jobs.id', ondelete='SET NULL'), nullable=True))
    op.create_index('idx_sales_upload_job_id', 'sales', ['upload_job_id'])
    # Backfill upload_job_id from upload_id if present
    op.execute("UPDATE sales SET upload_job_id = upload_id WHERE upload_job_id IS NULL AND upload_id IS NOT NULL")

    # 7. Add composite index on daily_product_demand (dataset_id, product_id, date_)
    op.create_index('idx_daily_demand_dataset_product_date', 'daily_product_demand', ['dataset_id', 'product_id', 'date_'])


def downgrade() -> None:
    op.drop_index('idx_daily_demand_dataset_product_date', table_name='daily_product_demand')
    op.drop_index('idx_sales_upload_job_id', table_name='sales')
    op.drop_column('sales', 'upload_job_id')
    op.drop_index('idx_daily_demand_upload_job_id', table_name='daily_product_demand')
    op.drop_column('daily_product_demand', 'upload_job_id')

    scoped_tables = [
        'sales',
        'daily_product_demand',
        'forecast_runs',
        'forecasts',
        'inventory_recommendations',
        'anomalies'
    ]
    for tbl in scoped_tables:
        op.drop_constraint(f'{tbl}_dataset_id_fkey', tbl, type_='foreignkey')
        op.drop_index(f'idx_{tbl}_dataset_id', table_name=tbl)
        op.drop_column(tbl, 'dataset_id')

    op.drop_index('idx_sku_mappings_dataset_sku', table_name='sku_mappings')
    op.drop_index('idx_sku_mappings_external_sku', table_name='sku_mappings')
    op.drop_table('sku_mappings')

    op.drop_column('products', 'source_upload_job_id')
    op.drop_column('products', 'is_provisional')

    op.drop_index('idx_datasets_user_active', table_name='datasets')
    op.drop_table('datasets')
