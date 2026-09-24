"""Phase 3: Engineering and safety schema extensions

Revision ID: 005_phase3
Revises: 004_phase2
Create Date: 2026-09-20 23:51:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '005_phase3'
down_revision = '004_phase2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('upload_jobs')]

    if 'current_stage' not in existing_columns:
        op.add_column('upload_jobs', sa.Column('current_stage', sa.String(50), nullable=True, server_default='pending'))
    if 'progress_pct' not in existing_columns:
        op.add_column('upload_jobs', sa.Column('progress_pct', sa.Integer(), nullable=False, server_default='0'))
    if 'error_message' not in existing_columns:
        op.add_column('upload_jobs', sa.Column('error_message', sa.Text(), nullable=True))
    if 'saved_file_path' not in existing_columns:
        op.add_column('upload_jobs', sa.Column('saved_file_path', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('upload_jobs', 'saved_file_path')
    op.drop_column('upload_jobs', 'error_message')
    op.drop_column('upload_jobs', 'progress_pct')
    op.drop_column('upload_jobs', 'current_stage')
