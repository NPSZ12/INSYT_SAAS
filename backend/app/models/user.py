from sqlalchemy import Column, Integer, String, Text
from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)

    email = Column(String, default="")

    role = Column(String, nullable=False)
    status = Column(String, default="Active")

    password_hash = Column(String, nullable=False)

    workspace_access = Column(Text, default="[]")
    client_access = Column(Text, default="[]")
    project_access = Column(Text, default="[]")
    launches = Column(Text, default="[]")
    permissions = Column(Text, default="[]")