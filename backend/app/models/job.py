from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.database.connection import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="Queued")
    project_id = Column(String(255), nullable=True)
    requested_by = Column(String(255), nullable=True)
    input_blob_path = Column(Text, nullable=True)
    output_blob_path = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())