"""Prompt Fix 1: Active dataset support and reconciliation of fragmented datasets (24, 29, 46)
Revision ID: 011_active_dataset
Revises: 010_models_and_quality
Create Date: 2026-09-21 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '011_active_dataset'
down_revision = '010_models_and_quality'

branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Update datasets table
    if 'datasets' in existing_tables:
        ds_cols = [c['name'] for c in inspector.get_columns('datasets')]
        if 'is_default_upload_target' not in ds_cols:
            op.add_column(
                'datasets',
                sa.Column('is_default_upload_target', sa.Boolean(), nullable=False, server_default='false')
            )
            op.create_index('ix_datasets_is_default_upload_target', 'datasets', ['is_default_upload_target'])

        if 'status' not in ds_cols:
            op.add_column(
                'datasets',
                sa.Column('status', sa.String(50), nullable=False, server_default='active')
            )

    # 2. Update users table with active_dataset_id
    if 'users' in existing_tables:
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'active_dataset_id' not in user_cols:
            op.add_column(
                'users',
                sa.Column(
                    'active_dataset_id',
                    sa.Integer(),
                    sa.ForeignKey('datasets.id', ondelete='SET NULL'),
                    nullable=True
                )
            )

    # 3. Data reconciliation: Reconcile datasets 24, 29, 46
    # Check if dataset 24 exists
    ds24_exists = conn.execute(sa.text("SELECT id FROM datasets WHERE id = 24")).fetchone()
    if ds24_exists:
        # Before counts
        r24_before = conn.execute(sa.text("SELECT COUNT(*) FROM daily_product_demand WHERE dataset_id = 24")).scalar()
        r29_before = conn.execute(sa.text("SELECT COUNT(*) FROM daily_product_demand WHERE dataset_id = 29")).scalar()
        r46_before = conn.execute(sa.text("SELECT COUNT(*) FROM daily_product_demand WHERE dataset_id = 46")).scalar()
        print(f"[RECONCILIATION BEFORE] Dataset 24 demand rows: {r24_before}, Dataset 29: {r29_before}, Dataset 46: {r46_before}")

        # Repoint any daily_product_demand from 29 and 46 to 24
        conn.execute(sa.text("UPDATE daily_product_demand SET dataset_id = 24 WHERE dataset_id IN (29, 46)"))
        conn.execute(sa.text("UPDATE sales SET dataset_id = 24 WHERE dataset_id IN (29, 46)"))

        # Mark 29 and 46 as merged
        conn.execute(sa.text("UPDATE datasets SET status = 'merged', is_active = false, is_default_upload_target = false WHERE id IN (29, 46)"))

        # Mark 24 as active default upload target
        conn.execute(sa.text("UPDATE datasets SET status = 'active', is_active = true, is_default_upload_target = true WHERE id = 24"))

        # Set active_dataset_id = 24 for all users
        conn.execute(sa.text("UPDATE users SET active_dataset_id = 24 WHERE active_dataset_id IS NULL"))

        r24_after = conn.execute(sa.text("SELECT COUNT(*) FROM daily_product_demand WHERE dataset_id = 24")).scalar()
        print(f"[RECONCILIATION AFTER] Dataset 24 demand rows: {r24_after} (merged 29 & 46)")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'users' in existing_tables:
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'active_dataset_id' in user_cols:
            op.drop_column('users', 'active_dataset_id')

    if 'datasets' in existing_tables:
        ds_cols = [c['name'] for c in inspector.get_columns('datasets')]
        if 'is_default_upload_target' in ds_cols:
            op.drop_index('ix_datasets_is_default_upload_target', 'datasets')
            op.drop_column('datasets', 'is_default_upload_target')
        if 'status' in ds_cols:
            op.drop_column('datasets', 'status')
