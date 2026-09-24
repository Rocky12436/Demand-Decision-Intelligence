"""
backend/models/calendar.py
--------------------------
SQLAlchemy models for the Indian Festival & Holiday Calendar (Prompt 5.1)
"""

from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Index
from sqlalchemy.sql import func
from backend.db.session import Base


class CalendarEvent(Base):
    """
    Stores Indian national holidays, religious festivals (lunar/moveable),
    regional festivals, month-end, and payday effects with impact windows.
    """
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_name = Column(String(100), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    # Event types: national_holiday, religious_festival, regional_festival, school_holiday, month_end, payday, custom
    event_type = Column(String(50), nullable=False, default="religious_festival", index=True)
    # Region / State code (e.g. 'DL', 'MH', 'KA', 'TN', 'WB', or NULL for national)
    region = Column(String(50), nullable=True, index=True)
    impact_window_before = Column(Integer, nullable=False, default=3)  # days before festival with demand ramp-up
    impact_window_after = Column(Integer, nullable=False, default=1)   # days after festival
    is_moveable = Column(Boolean, nullable=False, default=True)        # True if lunar/moveable date
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_cal_event_date_region", "event_date", "region"),
        Index("idx_cal_event_type", "event_type"),
    )
