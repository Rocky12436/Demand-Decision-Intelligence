"""Phase 4: The missing action layer schema extensions

Revision ID: 006_phase4
Revises: 005_phase3
Create Date: 2026-09-21 01:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '006_phase4'
down_revision = '005_phase3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Product additions
    if 'products' in existing_tables:
        prod_cols = [c['name'] for c in inspector.get_columns('products')]
        if 'shelf_life_days' not in prod_cols:
            op.add_column('products', sa.Column('shelf_life_days', sa.Integer(), nullable=True, server_default='180'))
        if 'storage_footprint' not in prod_cols:
            op.add_column('products', sa.Column('storage_footprint', sa.Float(), nullable=True, server_default='1.0'))

    # 2. User additions
    if 'users' in existing_tables:
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'approval_limit_value' not in user_cols:
            op.add_column('users', sa.Column('approval_limit_value', sa.Float(), nullable=False, server_default='50000.0'))

    # 3. Suppliers & Purchase Orders
    if 'suppliers' not in existing_tables:
        op.create_table(
            'suppliers',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
            sa.Column('contact_email', sa.String(255), nullable=True),
            sa.Column('contact_phone', sa.String(50), nullable=True),
            sa.Column('address', sa.Text(), nullable=True),
            sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('min_order_value', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'supplier_products' not in existing_tables:
        op.create_table(
            'supplier_products',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('unit_cost', sa.Float(), nullable=False, server_default='10.0'),
            sa.Column('moq', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('order_multiple', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('promised_lead_time_days', sa.Integer(), nullable=False, server_default='5'),
            sa.Column('is_preferred', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'purchase_orders' not in existing_tables:
        op.create_table(
            'purchase_orders',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('po_number', sa.String(100), nullable=False, unique=True, index=True),
            sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='RESTRICT'), nullable=False, index=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft', index=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expected_delivery_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('total_value', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('currency', sa.String(10), nullable=False, server_default='INR'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('triggered_by', sa.String(50), nullable=False, server_default='rop_breach'),
            sa.Column('source_policy_id', sa.String(100), nullable=True),
        )

    if 'purchase_order_lines' not in existing_tables:
        op.create_table(
            'purchase_order_lines',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='RESTRICT'), nullable=False, index=True),
            sa.Column('quantity_ordered', sa.Integer(), nullable=False),
            sa.Column('quantity_received', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('unit_cost', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('line_total', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('reason_code', sa.String(100), nullable=False, server_default='ROP_BREACH'),
            sa.Column('context_data', sa.Text(), nullable=True),
        )

    if 'goods_receipts' not in existing_tables:
        op.create_table(
            'goods_receipts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('po_id', sa.Integer(), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('received_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
        )

    if 'goods_receipt_lines' not in existing_tables:
        op.create_table(
            'goods_receipt_lines',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('receipt_id', sa.Integer(), sa.ForeignKey('goods_receipts.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('po_line_id', sa.Integer(), sa.ForeignKey('purchase_order_lines.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('condition_notes', sa.String(255), nullable=True),
        )

    # 4. Recommendations & Feedback
    if 'recommendations' not in existing_tables:
        op.create_table(
            'recommendations',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('city_name', sa.String(100), nullable=False, server_default='ALL', index=True),
            sa.Column('type', sa.String(50), nullable=False, server_default='reorder', index=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='NEW', index=True),
            sa.Column('recommended_qty', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('rationale_json', sa.JSON(), nullable=True),
            sa.Column('expected_value_impact', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('actioned_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('actioned_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
        )

    if 'recommendation_events' not in existing_tables:
        op.create_table(
            'recommendation_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('recommendations.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('from_status', sa.String(50), nullable=False),
            sa.Column('to_status', sa.String(50), nullable=False),
            sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'forecast_accuracy' not in existing_tables:
        op.create_table(
            'forecast_accuracy',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('city_name', sa.String(100), nullable=False, server_default='ALL', index=True),
            sa.Column('horizon_date', sa.Date(), nullable=False, index=True),
            sa.Column('predicted_demand', sa.Float(), nullable=False),
            sa.Column('actual_demand', sa.Float(), nullable=False),
            sa.Column('abs_error', sa.Float(), nullable=False),
            sa.Column('ape', sa.Float(), nullable=False),
            sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 5. Alerting
    if 'alert_rules' not in existing_tables:
        op.create_table(
            'alert_rules',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('type', sa.String(50), nullable=False, index=True),
            sa.Column('threshold_json', sa.JSON(), nullable=True),
            sa.Column('channels', sa.JSON(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('quiet_hours_start', sa.Integer(), nullable=True),
            sa.Column('quiet_hours_end', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'alerts' not in existing_tables:
        op.create_table(
            'alerts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('rule_id', sa.Integer(), sa.ForeignKey('alert_rules.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=True, index=True),
            sa.Column('type', sa.String(50), nullable=False, index=True),
            sa.Column('severity', sa.String(20), nullable=False, server_default='warning', index=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('payload_json', sa.JSON(), nullable=True),
            sa.Column('fired_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
            sa.Column('dedup_key', sa.String(64), nullable=False, index=True),
            sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('acknowledged_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
        )

    # 6. Inter-City Transfers
    if 'locations' not in existing_tables:
        op.create_table(
            'locations',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('city_name', sa.String(100), nullable=False, unique=True, index=True),
            sa.Column('location_type', sa.String(50), nullable=False, server_default='warehouse'),
            sa.Column('address', sa.Text(), nullable=True),
            sa.Column('lat', sa.Float(), nullable=False, server_default='12.9716'),
            sa.Column('lng', sa.Float(), nullable=False, server_default='77.5946'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'transfer_lanes' not in existing_tables:
        op.create_table(
            'transfer_lanes',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('from_location_id', sa.Integer(), sa.ForeignKey('locations.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('to_location_id', sa.Integer(), sa.ForeignKey('locations.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('transit_days', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('cost_per_unit', sa.Float(), nullable=False, server_default='1.5'),
            sa.Column('cost_fixed', sa.Float(), nullable=False, server_default='200.0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if 'transfer_orders' not in existing_tables:
        op.create_table(
            'transfer_orders',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, server_default='1', index=True),
            sa.Column('from_location_id', sa.Integer(), sa.ForeignKey('locations.id', ondelete='RESTRICT'), nullable=False, index=True),
            sa.Column('to_location_id', sa.Integer(), sa.ForeignKey('locations.id', ondelete='RESTRICT'), nullable=False, index=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft', index=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('expected_arrival', sa.DateTime(timezone=True), nullable=True),
            sa.Column('total_cost', sa.Float(), nullable=False, server_default='0.0'),
        )

    if 'transfer_order_lines' not in existing_tables:
        op.create_table(
            'transfer_order_lines',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('transfer_order_id', sa.Integer(), sa.ForeignKey('transfer_orders.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('product_id', sa.String(100), sa.ForeignKey('products.product_id', ondelete='RESTRICT'), nullable=False, index=True),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('reason', sa.String(255), nullable=True),
        )


def downgrade() -> None:
    op.drop_table('transfer_order_lines')
    op.drop_table('transfer_orders')
    op.drop_table('transfer_lanes')
    op.drop_table('locations')
    op.drop_table('alerts')
    op.drop_table('alert_rules')
    op.drop_table('forecast_accuracy')
    op.drop_table('recommendation_events')
    op.drop_table('recommendations')
    op.drop_table('goods_receipt_lines')
    op.drop_table('goods_receipts')
    op.drop_table('purchase_order_lines')
    op.drop_table('purchase_orders')
    op.drop_table('supplier_products')
    op.drop_table('suppliers')
    op.drop_column('users', 'approval_limit_value')
    op.drop_column('products', 'storage_footprint')
    op.drop_column('products', 'shelf_life_days')
