from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime

from app.database.connection import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    actor_username = Column(String, index=True)
    actor_email = Column(String, index=True)
    actor_role = Column(String, index=True)

    action = Column(String, index=True)
    target_type = Column(String, index=True)
    target_id = Column(String, index=True)

    workspace = Column(String, default="")
    client = Column(String, default="")
    project = Column(String, default="")

    ip_address = Column(String, default="")
    user_agent = Column(Text, default="")

    details = Column(Text, default="{}")