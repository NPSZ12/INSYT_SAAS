#!/usr/bin/env python3
"""Database-backed INSYT API startup regression for isolated CI."""

import os
import secrets
import sys
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    raise SystemExit("STOP: Python 3.12 required.")

if os.getenv("GITHUB_ACTIONS") != "true":
    raise SystemExit("STOP: CI-only test.")

root = Path(__file__).resolve().parents[1]
backend = root / "backend"
cyber2 = backend / "app/api/cyber2"

if cyber2.resolve() in {
    Path(p or os.getcwd()).resolve() for p in sys.path
}:
    raise SystemExit("STOP: Artificial Cyber2 import path.")

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.update({
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_DB": "insyt_release_validation",
    "POSTGRES_USER": "insyt_ci",
    "POSTGRES_PASSWORD": "synthetic_ci_only_password",
    "KEY_VAULT_URL": "",
    "JWT_SECRET_KEY": secrets.token_urlsafe(48),
})

sys.path.insert(0, str(backend))

from psycopg2 import connect

probe = connect(
    host="127.0.0.1",
    port=5432,
    dbname="insyt_release_validation",
    user="insyt_ci",
    password="synthetic_ci_only_password",
    sslmode="require",
    connect_timeout=5,
)

try:
    if not probe.info.ssl_in_use:
        raise SystemExit("STOP: Test database connection lacks TLS.")
finally:
    probe.close()

print("PASS: Disposable PostgreSQL connection uses TLS.")

from sqlalchemy import inspect, text
from app.database.connection import engine, SessionLocal
from app.models.user import User

if inspect(engine).get_table_names():
    raise SystemExit("STOP: Test database is not empty.")

# Bootstrap an existing-style users table without changing
# the production model, schema initializer or migration.
User.__table__.create(bind=engine)

# Seed while the complete SQLAlchemy model still matches
# the initial table. This avoids default-admin creation.
session = SessionLocal()
try:
    session.add(User(
        username="admin",
        display_name="Synthetic CI User",
        email="synthetic@example.invalid",
        role="Admin",
        status="Active",
        password_hash="synthetic-not-a-real-password-hash",
    ))
    session.commit()
finally:
    session.close()

migration_columns = (
    "workspace_access",
    "client_access",
    "auth_provider",
    "mfa_enabled",
    "mfa_secret",
    "mfa_backup_codes",
    "mfa_confirmed_at",
)

# Simulate an older users table. The real INSYT migration
# must restore these columns during app.main import.
with engine.begin() as connection:
    for column in migration_columns:
        connection.execute(
            text(f'ALTER TABLE users DROP COLUMN "{column}"')
        )

from fastapi import FastAPI
from app.main import app

if not isinstance(app, FastAPI):
    raise SystemExit("STOP: FastAPI app missing.")

columns = {
    item["name"]
    for item in inspect(engine).get_columns("users")
}

if not set(migration_columns).issubset(columns):
    raise SystemExit("STOP: Existing migration failed.")

if not app.openapi().get("paths"):
    raise SystemExit("STOP: API route registration failed.")

print("PASS: Actual user/MFA migrations executed.")
print("PASS: Actual database initialization executed.")
print("PASS: Complete app.main imported.")
print("PASS: OpenAPI routes available:", len(app.routes))
