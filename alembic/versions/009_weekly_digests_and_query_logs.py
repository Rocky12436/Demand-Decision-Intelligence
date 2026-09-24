"""Prompt 5.5 & 5.6: Weekly Digests and Query Logs
Revision ID: 009_digests_and_nl_query
Revises: 008_festival_and_quantiles
Create Date: 2026-09-21 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '009_digests_and_nl_query'
down_revision = '008_festival_and_quantiles'

branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. weekly_digests table
    if 'weekly_digests' not in existing_tables:
        op.create_table(
            'weekly_digests',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('week_start_date', sa.Date(), nullable=False),
            sa.Column('week_end_date', sa.Date(), nullable=False),
            sa.Column('headline', sa.String(length=255), nullable=False),
            sa.Column('narrative_prose', sa.Text(), nullable=False),
            sa.Column('structured_numbers', sa.JSON(), nullable=False),
            sa.Column('delivered_email', sa.String(length=255), nullable=True),
            sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_digest_dataset_dates', 'weekly_digests', ['dataset_id', 'week_start_date', 'week_end_date'])

    # 2. Add query metadata columns to chat_messages if not exists
    if 'chat_messages' in existing_tables:
        existing_cols = [c['name'] for c in inspector.get_columns('chat_messages')]
        if 'query_template' not in existing_cols:
            op.add_column('chat_messages', sa.Column('query_template', sa.String(length=100), nullable=True))
        if 'template_params' not in existing_cols:
            op.add_column('chat_messages', sa.Column('template_params', sa.JSON(), nullable=True))
        if 'execution_ms' not in existing_cols:
            op.add_column('chat_messages', sa.Column('execution_ms', sa.Float(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'weekly_digests' in existing_tables:
        op.drop_index('idx_digest_dataset_dates', table_name='weekly_digests')
        op.drop_table('weekly_digests')

    if 'chat_messages' in existing_tables:
        existing_cols = [c['name'] for c in inspector.get_columns('chat_messages')]
        if 'execution_ms' in existing_cols:
            op.drop_column('chat_messages', 'execution_ms')
        if 'template_params' in existing_cols:
            op.drop_column('chat_messages', 'template_params')
        if 'query_template' in existing_cols:
            op.drop_column('chat_messages', 'query_template')
