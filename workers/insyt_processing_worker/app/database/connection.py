import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_DB = os.getenv("POSTGRES_DB", "insyt_capture")
POSTGRES_USER = os.getenv("POSTGRES_USER")

KEY_VAULT_URL = os.getenv("KEY_VAULT_URL")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

if KEY_VAULT_URL:
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    POSTGRES_PASSWORD = secret_client.get_secret("postgres-password").value

if not all([POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]):
    raise RuntimeError(
        "Missing PostgreSQL configuration. Required: POSTGRES_HOST, POSTGRES_DB, "
        "POSTGRES_USER, and either POSTGRES_PASSWORD or KEY_VAULT_URL."
    )

DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:5432/{POSTGRES_DB}?sslmode=require"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()