"""Prompt 5.1 & 5.2: Indian Festival Calendar and Probabilistic Quantiles

Revision ID: 008_festival_and_quantiles
Revises: 007_abc_xyz_and_dead_stock
Create Date: 2026-09-21 12:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from datetime import date

revision = '008_festival_and_quantiles'
down_revision = '007_abc_xyz_and_dead_stock'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. calendar_events table
    if 'calendar_events' not in existing_tables:
        op.create_table(
            'calendar_events',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('event_name', sa.String(length=100), nullable=False),
            sa.Column('event_date', sa.Date(), nullable=False),
            sa.Column('event_type', sa.String(length=50), nullable=False, server_default='religious_festival'),
            sa.Column('region', sa.String(length=50), nullable=True),
            sa.Column('impact_window_before', sa.Integer(), nullable=False, server_default='3'),
            sa.Column('impact_window_after', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_moveable', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_cal_event_date_region', 'calendar_events', ['event_date', 'region'])
        op.create_index('idx_cal_event_type', 'calendar_events', ['event_type'])

        # Seed 2020-2030 Indian festival calendar events
        calendar_table = table(
            'calendar_events',
            column('event_name', sa.String),
            column('event_date', sa.Date),
            column('event_type', sa.String),
            column('region', sa.String),
            column('impact_window_before', sa.Integer),
            column('impact_window_after', sa.Integer),
            column('is_moveable', sa.Boolean),
        )

        events_to_seed = []

        # Fixed annual dates 2020-2030
        for yr in range(2020, 2031):
            events_to_seed.extend([
                {'event_name': 'New Year', 'event_date': date(yr, 1, 1), 'event_type': 'national_holiday', 'region': None, 'impact_window_before': 2, 'impact_window_after': 1, 'is_moveable': False},
                {'event_name': 'Makar Sankranti', 'event_date': date(yr, 1, 14), 'event_type': 'religious_festival', 'region': None, 'impact_window_before': 2, 'impact_window_after': 1, 'is_moveable': False},
                {'event_name': 'Pongal', 'event_date': date(yr, 1, 15), 'event_type': 'regional_festival', 'region': 'TN', 'impact_window_before': 3, 'impact_window_after': 1, 'is_moveable': False},
                {'event_name': 'Republic Day', 'event_date': date(yr, 1, 26), 'event_type': 'national_holiday', 'region': None, 'impact_window_before': 1, 'impact_window_after': 0, 'is_moveable': False},
                {'event_name': 'Independence Day', 'event_date': date(yr, 8, 15), 'event_type': 'national_holiday', 'region': None, 'impact_window_before': 1, 'impact_window_after': 0, 'is_moveable': False},
                {'event_name': 'Christmas', 'event_date': date(yr, 12, 25), 'event_type': 'religious_festival', 'region': None, 'impact_window_before': 4, 'impact_window_after': 1, 'is_moveable': False},
            ])
            # Payday and Month-End for each month
            for m in range(1, 13):
                events_to_seed.append({
                    'event_name': f'Payday {yr}-{m:02d}', 'event_date': date(yr, m, 1), 'event_type': 'payday', 'region': None, 'impact_window_before': 0, 'impact_window_after': 3, 'is_moveable': False
                })

        # Moveable Lunar Festivals per year (2020-2030)
        lunar_data = {
            'Holi': {
                2020: date(2020, 3, 10), 2021: date(2021, 3, 29), 2022: date(2022, 3, 18), 2023: date(2023, 3, 8),
                2024: date(2024, 3, 25), 2025: date(2025, 3, 14), 2026: date(2026, 3, 4), 2027: date(2027, 3, 22),
                2028: date(2028, 3, 11), 2029: date(2029, 2, 28), 2030: date(2030, 3, 19),
            },
            'Gudi Padwa': {
                2020: date(2020, 3, 25), 2021: date(2021, 4, 13), 2022: date(2022, 4, 2), 2023: date(2023, 3, 22),
                2024: date(2024, 4, 9), 2025: date(2025, 3, 30), 2026: date(2026, 3, 19), 2027: date(2027, 4, 7),
                2028: date(2028, 3, 27), 2029: date(2029, 4, 14), 2030: date(2030, 4, 3),
            },
            'Eid al-Fitr': {
                2020: date(2020, 5, 24), 2021: date(2021, 5, 13), 2022: date(2022, 5, 2), 2023: date(2023, 4, 21),
                2024: date(2024, 4, 10), 2025: date(2025, 3, 30), 2026: date(2026, 3, 20), 2027: date(2027, 3, 9),
                2028: date(2028, 2, 26), 2029: date(2029, 2, 15), 2030: date(2030, 2, 4),
            },
            'Eid al-Adha': {
                2020: date(2020, 7, 31), 2021: date(2021, 7, 20), 2022: date(2022, 7, 10), 2023: date(2023, 6, 29),
                2024: date(2024, 6, 17), 2025: date(2025, 6, 6), 2026: date(2026, 5, 27), 2027: date(2027, 5, 16),
                2028: date(2028, 5, 5), 2029: date(2029, 4, 24), 2030: date(2030, 4, 14),
            },
            'Raksha Bandhan': {
                2020: date(2020, 8, 3), 2021: date(2021, 8, 22), 2022: date(2022, 8, 11), 2023: date(2023, 8, 30),
                2024: date(2024, 8, 19), 2025: date(2025, 8, 9), 2026: date(2026, 8, 28), 2027: date(2027, 8, 17),
                2028: date(2028, 8, 5), 2029: date(2029, 8, 24), 2030: date(2030, 8, 13),
            },
            'Ganesh Chaturthi': {
                2020: date(2020, 8, 22), 2021: date(2021, 9, 10), 2022: date(2022, 8, 31), 2023: date(2023, 9, 19),
                2024: date(2024, 9, 7), 2025: date(2025, 8, 27), 2026: date(2026, 9, 14), 2027: date(2027, 9, 4),
                2028: date(2028, 8, 23), 2029: date(2029, 9, 11), 2030: date(2030, 8, 31),
            },
            'Onam': {
                2020: date(2020, 8, 31), 2021: date(2021, 8, 21), 2022: date(2022, 9, 8), 2023: date(2023, 8, 29),
                2024: date(2024, 9, 15), 2025: date(2025, 9, 5), 2026: date(2026, 8, 26), 2027: date(2027, 9, 12),
                2028: date(2028, 9, 1), 2029: date(2029, 8, 21), 2030: date(2030, 9, 9),
            },
            'Dussehra': {
                2020: date(2020, 10, 25), 2021: date(2021, 10, 15), 2022: date(2022, 10, 5), 2023: date(2023, 10, 24),
                2024: date(2024, 10, 12), 2025: date(2025, 10, 2), 2026: date(2026, 10, 20), 2027: date(2027, 10, 9),
                2028: date(2028, 9, 28), 2029: date(2029, 10, 17), 2030: date(2030, 10, 6),
            },
            'Durga Puja': {
                2020: date(2020, 10, 24), 2021: date(2021, 10, 14), 2022: date(2022, 10, 4), 2023: date(2023, 10, 23),
                2024: date(2024, 10, 11), 2025: date(2025, 10, 1), 2026: date(2026, 10, 19), 2027: date(2027, 10, 8),
                2028: date(2028, 9, 27), 2029: date(2029, 10, 16), 2030: date(2030, 10, 5),
            },
            'Dhanteras': {
                2020: date(2020, 11, 12), 2021: date(2021, 11, 2), 2022: date(2022, 10, 22), 2023: date(2023, 11, 10),
                2024: date(2024, 10, 29), 2025: date(2025, 10, 18), 2026: date(2026, 11, 6), 2027: date(2027, 10, 27),
                2028: date(2028, 11, 14), 2029: date(2029, 11, 3), 2030: date(2030, 10, 24),
            },
            'Diwali': {
                2020: date(2020, 11, 14), 2021: date(2021, 11, 4), 2022: date(2022, 10, 24), 2023: date(2023, 11, 12),
                2024: date(2024, 10, 31), 2025: date(2025, 10, 20), 2026: date(2026, 11, 8), 2027: date(2027, 10, 29),
                2028: date(2028, 11, 16), 2029: date(2029, 11, 5), 2030: date(2030, 10, 26),
            },
        }

        for ev_name, yr_dict in lunar_data.items():
            reg = 'MH' if ev_name in ['Gudi Padwa', 'Ganesh Chaturthi'] else ('KL' if ev_name == 'Onam' else ('WB' if ev_name == 'Durga Puja' else None))
            w_before = 7 if ev_name in ['Diwali', 'Dhanteras', 'Dussehra', 'Durga Puja'] else (4 if ev_name in ['Holi', 'Eid al-Fitr'] else 2)
            w_after = 2 if ev_name in ['Diwali', 'Holi'] else 1

            for yr, dt in yr_dict.items():
                events_to_seed.append({
                    'event_name': ev_name,
                    'event_date': dt,
                    'event_type': 'religious_festival',
                    'region': reg,
                    'impact_window_before': w_before,
                    'impact_window_after': w_after,
                    'is_moveable': True,
                })

        op.bulk_insert(calendar_table, events_to_seed)

    # 2. Add quantiles column to forecasts table (ForecastItem)
    if 'forecasts' in existing_tables:
        forecast_cols = [c['name'] for c in inspector.get_columns('forecasts')]
        if 'quantiles' not in forecast_cols:
            op.add_column('forecasts', sa.Column('quantiles', sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'forecasts' in existing_tables:
        forecast_cols = [c['name'] for c in inspector.get_columns('forecasts')]
        if 'quantiles' in forecast_cols:
            op.drop_column('forecasts', 'quantiles')

    if 'calendar_events' in existing_tables:
        op.drop_table('calendar_events')
