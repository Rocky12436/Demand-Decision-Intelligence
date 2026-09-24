"""Prompt 4.7 & 4.8: ABC-XYZ Classification Policies and Dead Stock Actions

Revision ID: 007_abc_xyz_and_dead_stock
Revises: 006_phase4
Create Date: 2026-09-21 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision = '007_abc_xyz_and_dead_stock'
down_revision = '006_phase4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. abc_xyz_policies table
    if 'abc_xyz_policies' not in existing_tables:
        op.create_table(
            'abc_xyz_policies',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('cell', sa.String(length=2), nullable=False, unique=True),
            sa.Column('abc_class', sa.String(length=1), nullable=False),
            sa.Column('xyz_class', sa.String(length=1), nullable=False),
            sa.Column('review_strategy', sa.String(length=50), nullable=False, server_default='CONTINUOUS'),
            sa.Column('target_service_level', sa.Float(), nullable=False, server_default='0.95'),
            sa.Column('safety_stock_policy', sa.String(length=100), nullable=False, server_default='STANDARD_KINGS'),
            sa.Column('reorder_automation', sa.String(length=50), nullable=False, server_default='AUTOMATED'),
            sa.Column('review_frequency_days', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_abc_xyz_cell', 'abc_xyz_policies', ['cell'], unique=True)

        # Seed initial 9 cells specified in Prompt 4.7
        policies_table = table(
            'abc_xyz_policies',
            column('cell', sa.String),
            column('abc_class', sa.String),
            column('xyz_class', sa.String),
            column('review_strategy', sa.String),
            column('target_service_level', sa.Float),
            column('safety_stock_policy', sa.String),
            column('reorder_automation', sa.String),
            column('review_frequency_days', sa.Integer),
            column('description', sa.String),
        )
        op.bulk_insert(
            policies_table,
            [
                {
                    'cell': 'AX',
                    'abc_class': 'A',
                    'xyz_class': 'X',
                    'review_strategy': 'CONTINUOUS',
                    'target_service_level': 0.98,
                    'safety_stock_policy': 'STANDARD_KINGS',
                    'reorder_automation': 'AUTOMATED',
                    'review_frequency_days': 1,
                    'description': 'Tight continuous review, high service level (98%), automated reorder'
                },
                {
                    'cell': 'AY',
                    'abc_class': 'A',
                    'xyz_class': 'Y',
                    'review_strategy': 'CONTINUOUS',
                    'target_service_level': 0.95,
                    'safety_stock_policy': 'HIGHER_SAFETY_STOCK',
                    'reorder_automation': 'MANUAL_APPROVAL',
                    'review_frequency_days': 3,
                    'description': 'Continuous review, higher safety stock, manual approval'
                },
                {
                    'cell': 'AZ',
                    'abc_class': 'A',
                    'xyz_class': 'Z',
                    'review_strategy': 'CONTINUOUS',
                    'target_service_level': 0.95,
                    'safety_stock_policy': 'STRATEGIC_BUFFER',
                    'reorder_automation': 'HUMAN_REVIEW',
                    'review_frequency_days': 7,
                    'description': 'Continuous review, high safety stock, strategic buffer, human review'
                },
                {
                    'cell': 'BX',
                    'abc_class': 'B',
                    'xyz_class': 'X',
                    'review_strategy': 'PERIODIC',
                    'target_service_level': 0.95,
                    'safety_stock_policy': 'STANDARD_KINGS',
                    'reorder_automation': 'AUTOMATED',
                    'review_frequency_days': 7,
                    'description': 'Periodic review, standard service level (95%)'
                },
                {
                    'cell': 'BY',
                    'abc_class': 'B',
                    'xyz_class': 'Y',
                    'review_strategy': 'PERIODIC',
                    'target_service_level': 0.92,
                    'safety_stock_policy': 'MODERATE_STOCK',
                    'reorder_automation': 'MANUAL_APPROVAL',
                    'review_frequency_days': 14,
                    'description': 'Periodic review, moderate stock, watch closely'
                },
                {
                    'cell': 'BZ',
                    'abc_class': 'B',
                    'xyz_class': 'Z',
                    'review_strategy': 'PERIODIC',
                    'target_service_level': 0.90,
                    'safety_stock_policy': 'MODERATE_STOCK',
                    'reorder_automation': 'MANUAL_APPROVAL',
                    'review_frequency_days': 14,
                    'description': 'Periodic review, moderate stock, watch closely'
                },
                {
                    'cell': 'CX',
                    'abc_class': 'C',
                    'xyz_class': 'X',
                    'review_strategy': 'MIN_MAX',
                    'target_service_level': 0.90,
                    'safety_stock_policy': 'LOW_TOUCH_MINIMAL',
                    'reorder_automation': 'AUTOMATED',
                    'review_frequency_days': 30,
                    'description': 'Simple min/max, long review period, low touch'
                },
                {
                    'cell': 'CY',
                    'abc_class': 'C',
                    'xyz_class': 'Y',
                    'review_strategy': 'MIN_MAX',
                    'target_service_level': 0.85,
                    'safety_stock_policy': 'CONSOLIDATE_SUPPLIER',
                    'reorder_automation': 'MANUAL_APPROVAL',
                    'review_frequency_days': 30,
                    'description': 'Min/max, consider consolidating suppliers'
                },
                {
                    'cell': 'CZ',
                    'abc_class': 'C',
                    'xyz_class': 'Z',
                    'review_strategy': 'MAKE_TO_ORDER',
                    'target_service_level': 0.0,
                    'safety_stock_policy': 'DO_NOT_HOLD_STOCK',
                    'reorder_automation': 'DO_NOT_STOCK',
                    'review_frequency_days': 60,
                    'description': 'Make-to-order or consider delisting; do not hold stock'
                },
            ]
        )

    # 2. product_classifications table
    if 'product_classifications' not in existing_tables:
        op.create_table(
            'product_classifications',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('product_id', sa.String(length=100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False),
            sa.Column('abc_class', sa.String(length=1), nullable=False),
            sa.Column('xyz_class', sa.String(length=1), nullable=False),
            sa.Column('cell', sa.String(length=2), nullable=False),
            sa.Column('annual_consumption_value', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('value_share_cumulative', sa.Float(), nullable=True, server_default='0.0'),
            sa.Column('cv2', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('mean_daily_demand', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('std_daily_demand', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('unit_cost', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_prod_class_dataset_cell', 'product_classifications', ['dataset_id', 'cell'])
        op.create_index('idx_prod_class_dataset_product', 'product_classifications', ['dataset_id', 'product_id'])

    # 3. dead_stock_records table
    if 'dead_stock_records' not in existing_tables:
        op.create_table(
            'dead_stock_records',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('product_id', sa.String(length=100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False),
            sa.Column('city_name', sa.String(length=100), nullable=False, server_default='ALL'),
            sa.Column('on_hand', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('unit_cost', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('selling_price', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('days_inactive', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('days_of_cover', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('capital_tied_up', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('monthly_storage_cost', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('projected_obsolescence_date', sa.Date(), nullable=True),
            sa.Column('recommended_action', sa.String(length=50), nullable=False, server_default='MARKDOWN'),
            sa.Column('suggested_discount_pct', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('elasticity_used', sa.Float(), nullable=True, server_default='-1.5'),
            sa.Column('is_assumption', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('projected_recovery_value', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('transfer_destination_city', sa.String(length=100), nullable=True),
            sa.Column('bundle_partner_product_id', sa.String(length=100), nullable=True),
            sa.Column('reasoning', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
            sa.Column('action_notes', sa.Text(), nullable=True),
            sa.Column('action_applied_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_dead_stock_dataset_status', 'dead_stock_records', ['dataset_id', 'status'])
        op.create_index('idx_dead_stock_dataset_action', 'dead_stock_records', ['dataset_id', 'recommended_action'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'dead_stock_records' in existing_tables:
        op.drop_table('dead_stock_records')
    if 'product_classifications' in existing_tables:
        op.drop_table('product_classifications')
    if 'abc_xyz_policies' in existing_tables:
        op.drop_table('abc_xyz_policies')
