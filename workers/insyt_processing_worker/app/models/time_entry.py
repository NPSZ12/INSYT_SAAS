from datetime import datetime, date

from sqlalchemy import Column, Date, DateTime, Float, Integer, String

from app.database.connection import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, index=True)

    workspace = Column(String, index=True)
    client = Column(String, index=True)
    project = Column(String, index=True)

    username = Column(String, index=True)
    display_name = Column(String, default="")
    role = Column(String, index=True)

    work_date = Column(Date, default=date.today, index=True)
    week_ending = Column(Date, index=True)

    hours = Column(Float, default=0.0)

    note = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)