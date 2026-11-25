#!/usr/bin/env python3
"""INSYT functional authentication regression on disposable CI PostgreSQL.

Executes actual FastAPI routes with synthetic users.
Never connects to Azure, Microsoft Entra, or production databases.
"""

import os
import secrets
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

if sys.version_info[:2] != (3, 12):
    raise SystemExit("STOP: Python 3.12 required.")

if os.getenv("GITHUB_ACTIONS") != "true":
    raise SystemExit("STOP: GitHub CI only.")

# Refuse to run outside the exact synthetic test environment.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

os.environ.update({
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_DB": "insyt_release_validation",
    "POSTGRES_USER": "insyt_ci",
    "POSTGRES_PASSWORD": "synthetic_ci_only_password",
    "KEY_VAULT_URL": "",
    "JWT_SECRET_KEY": secrets.token_urlsafe(48),
})

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))

import pyotp
from fastapi.testclient import TestClient
from psycopg2 import connect
from sqlalchemy import inspect
from app.database.connection import engine, SessionLocal
from app.models.user import User
from app.services.security import hash_password
from app.main import app
import app.api.auth as auth

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
        raise SystemExit("STOP: Synthetic PostgreSQL lacks TLS.")
finally:
    probe.close()

if "users" not in inspect(engine).get_table_names():
    raise SystemExit("STOP: Synthetic users table missing.")

required_routes = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/mfa/setup"),
    ("POST", "/api/auth/mfa/confirm"),
    ("POST", "/api/auth/mfa/disable"),
    ("POST", "/api/auth/entra-login"),
    ("POST", "/api/auth/entra-verified-login"),
    ("GET", "/api/auth/entra/start"),
    ("POST", "/api/auth/entra/callback"),
    ("GET", "/api/auth/me"),
}

registered = {
    (method, route.path)
    for route in app.routes
    for method in getattr(route, "methods", set())
}

missing = required_routes - registered
if missing:
    raise SystemExit("STOP: Authentication routes missing: " + str(sorted(missing)))

print("PASS: All nine protected login/MFA/Entra routes registered.")

username = "ci_auth_" + uuid.uuid4().hex[:16]
password = secrets.token_urlsafe(30)
email = username + "@example.invalid"

session = SessionLocal()

try:
    user = User(
        username=username,
        display_name="Synthetic Authentication Regression",
        email=email,
        role="INSYT Admin",
        status="Active",
        auth_provider="local",
        password_hash=hash_password(password),
        mfa_enabled=False,
        mfa_secret="",
        workspace_access="[]",
        client_access="[]",
        project_access="[]",
        launches="[]",
        permissions="[]",
    )
    session.add(user)
    session.commit()
finally:
    session.close()

def expect(response, code, *, status=None):
    if response.status_code != code:
        raise AssertionError(
            f"Expected HTTP {code}, received {response.status_code}: "
            + response.text[:350]
        )

    if status is not None and response.json().get("status") != status:
        raise AssertionError(
            f"Expected status {status!r}, "
            f"received {response.json().get('status')!r}"
        )

    return response.json()

try:
    # Suppress audit writes only because the synthetic database
    # intentionally contains no production audit-log tables.
    # The actual authentication handlers remain unchanged.
    with patch.object(auth, "write_audit_log"), TestClient(app) as client:

        missing_token = client.get("/api/auth/me")
        expect(missing_token, 401)
        print("PASS: Missing authentication token rejected.")

        invalid_token = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.synthetic.token"},
        )
        expect(invalid_token, 401)
        print("PASS: Invalid authentication token rejected.")

        incorrect = client.post(
            "/api/auth/login",
            json={"username": username, "password": "incorrect-password"},
        )
        expect(incorrect, 401)
        print("PASS: Incorrect administrator password rejected.")

        first_login = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        initial = expect(first_login, 200, status="mfa_setup_required")

        setup_token = initial.get("access_token")
        if not setup_token:
            raise AssertionError("MFA enrollment access token missing.")

        print("PASS: Synthetic administrator login requires MFA enrollment.")

        headers = {"Authorization": f"Bearer {setup_token}"}

        me = client.get("/api/auth/me", headers=headers)
        profile = expect(me, 200, status="success")

        if profile["user"]["username"] != username:
            raise AssertionError("Authenticated user mismatch.")

        print("PASS: Authenticated /me returns correct synthetic user.")

        setup = client.post("/api/auth/mfa/setup", headers=headers)
        enrollment = expect(setup, 200, status="success")

        secret = enrollment.get("manual_key")
        if not secret:
            raise AssertionError("MFA enrollment secret missing.")

        code = pyotp.TOTP(secret).now()
        wrong = f"{(int(code) + 1) % 1000000:06d}"

        invalid_confirmation = client.post(
            "/api/auth/mfa/confirm",
            headers=headers,
            json={"code": wrong},
        )
        expect(invalid_confirmation, 401)

        print("PASS: Incorrect MFA confirmation rejected.")

        confirmation = client.post(
            "/api/auth/mfa/confirm",
            headers=headers,
            json={"code": pyotp.TOTP(secret).now()},
        )
        expect(confirmation, 200, status="success")

        print("PASS: Synthetic MFA enrollment confirmed.")

        without_mfa = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        expect(without_mfa, 200, status="mfa_required")

        print("PASS: Administrator login requires MFA after enrollment.")

        incorrect_mfa = client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
                "mfa_code": wrong,
            },
        )
        expect(incorrect_mfa, 401)

        print("PASS: Incorrect login MFA code rejected.")

        correct_mfa = client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
                "mfa_code": pyotp.TOTP(secret).now(),
            },
        )
        result = expect(correct_mfa, 200, status="success")

        if not result.get("access_token"):
            raise AssertionError("Successful MFA login returned no token.")

        print("PASS: Administrator login succeeds with valid MFA.")

        authenticated = client.get(
            "/api/auth/me",
            headers={
                "Authorization": "Bearer " + result["access_token"]
            },
        )
        expect(authenticated, 200, status="success")

        print("PASS: Post-MFA access token works.")

        # No real Entra endpoint is contacted.
        with patch.dict(os.environ, {
            "ENTRA_CLIENT_ID": "insyt-ci-test-client",
            "ENTRA_TENANT_ID": "insyt-ci-test-tenant",
        }):
            start = client.get("/api/auth/entra/start")
            authorization = expect(start, 200, status="success")
            url = urlparse(authorization["auth_url"])
            params = parse_qs(url.query)

            if (
                url.hostname != "login.microsoftonline.com"
                or params.get("client_id") != ["insyt-ci-test-client"]
            ):
                raise AssertionError("Entra authorization URL mismatch.")

        print("PASS: Entra authorization URL constructed correctly.")

        missing_code = client.post(
            "/api/auth/entra/callback",
            json={},
        )
        expect(missing_code, 400)

        print("PASS: Incomplete Entra callback rejected.")

finally:
    # Synthetic data is removed even when an assertion fails.
    cleanup = SessionLocal()
    try:
        cleanup.query(User).filter(
            User.username == username
        ).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()

print("PASS: Complete candidate API authentication regression.")
print("PASS: No production credentials or Entra requests used.")
