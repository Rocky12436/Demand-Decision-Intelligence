"""phase2 statistical engines: lead time observations, anomaly classification, commodity mappings, price observations

Revision ID: 004_phase2
Revises: 003_idempotent
Create Date: 2026-09-20 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_phase2'
down_revision = '003_idempotent'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create lead_time_observations table
    op.create_table(
        'lead_time_observations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False),
        sa.Column('supplier_id', sa.String(100), nullable=True),
        sa.Column('po_id', sa.String(100), nullable=True),
        sa.Column('promised_days', sa.Integer(), nullable=False),
        sa.Column('actual_days', sa.Integer(), nullable=False),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_lto_dataset_id', 'lead_time_observations', ['dataset_id'])
    op.create_index('idx_lto_product_id', 'lead_time_observations', ['product_id'])
    op.create_index('idx_lto_supplier_id', 'lead_time_observations', ['supplier_id'])

    # 2. Add detection_method and confidence to anomalies table
    op.add_column('anomalies', sa.Column('detection_method', sa.String(100), nullable=True))
    op.add_column('anomalies', sa.Column('confidence', sa.String(20), nullable=True, server_default='MEDIUM'))

    # 3. Create commodity_mappings table
    op.create_table(
        'commodity_mappings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False),
        sa.Column('commodity_code', sa.String(50), nullable=False),
        sa.Column('commodity_name', sa.String(150), nullable=False),
        sa.Column('market_name', sa.String(100), nullable=False, server_default='ALL'),
        sa.Column('source_unit', sa.String(50), nullable=False, server_default='Rs/quintal'),
        sa.Column('conversion_factor_to_internal', sa.Float(), nullable=False, server_default='0.01'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_cm_product_id', 'commodity_mappings', ['product_id'])
    op.create_index('idx_cm_commodity_code', 'commodity_mappings', ['commodity_code'])

    # 4. Create price_observations table
    op.create_table(
        'price_observations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('commodity_code', sa.String(50), nullable=False),
        sa.Column('market_name', sa.String(100), nullable=False),
        sa.Column('observed_date', sa.Date(), nullable=False),
        sa.Column('wholesale_price', sa.Float(), nullable=True),
        sa.Column('retail_price', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(50), nullable=False),
        sa.Column('source', sa.String(100), nullable=False, server_default='fcainfoweb.nic.in'),
        sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_interpolated', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('idx_po_comm_date', 'price_observations', ['commodity_code', 'observed_date'])
    op.create_index('idx_po_observed_date', 'price_observations', ['observed_date'])

    # 5. Create category_price_thresholds table
    op.create_table(
        'category_price_thresholds',
        sa.Column('category_name', sa.String(100), primary_key=True),
        sa.Column('bulk_threshold_pct', sa.Float(), nullable=False, server_default='8.0'),
        sa.Column('trim_threshold_pct', sa.Float(), nullable=False, server_default='-8.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade() -> None:
    op.drop_table('category_price_thresholds')
    op.drop_table('price_observations')
    op.drop_table('commodity_mappings')
    op.drop_column('anomalies', 'confidence')
    op.drop_column('anomalies', 'detection_method')
    op.drop_table('lead_time_observations')
