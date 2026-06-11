from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.database.connection import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True, nullable=False)
    project_name = Column(String, nullable=False)
    client_name = Column(String, default="")
    status = Column(String, default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, index=True, nullable=False)
    batch_id = Column(String, index=True, nullable=False)
    batch_type = Column(String, default="review")
    status = Column(String, default="Available")
    checked_out_by = Column(String, default="")
    doc_ids = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentStatus(Base):
    __tablename__ = "document_status"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, index=True, nullable=False)
    batch_id = Column(String, index=True, nullable=False)
    doc_id = Column(String, index=True, nullable=False)
    status = Column(String, default="Not Started")
    reviewer = Column(String, default="")
    coding = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


class CapturedEntity(Base):
    __tablename__ = "captured_entities"

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(String, index=True, nullable=False)
    batch_id = Column(String, index=True, nullable=False)

    doc_id = Column(String, index=True, nullable=False)

    captured_by = Column(String, index=True, nullable=False)

    linked = Column(String, default="true")

    values = Column(Text, default="{}")

    # NEW — identifies where entity originated
    source_type = Column(String, default="MANUAL")

    # NEW — original imported spreadsheet name
    source_file = Column(String, default="")

    # NEW — original spreadsheet row number
    source_row = Column(Integer, default=0)

    # OPTIONAL — useful for auditing/mapping review
    import_group = Column(String, default="")

    created_at = Column(DateTime, default=datetime.utcnow)