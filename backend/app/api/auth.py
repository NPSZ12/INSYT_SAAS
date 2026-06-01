import base64
import io
import json
import os
from datetime import datetime
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = ""


class BootstrapAdminRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str


class MfaConfirmRequest(BaseModel):
    code: str


def safe_json_list(value: str):
    try:
        return json.loads(value or "[]")
    except Exception:
        return []


def serialize_user(user: User):
    return {
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "auth_provider": user.auth_provider,
        "mfa_enabled": user.mfa_enabled,
        "workspace_access": safe_json_list(user.workspace_access),
        "client_access": safe_json_list(user.client_access),
        "project_access": safe_json_list(user.project_access),
        "launches": safe_json_list(user.launches),
        "permissions": safe_json_list(user.permissions),
    }


def create_user_token(user: User):
    return create_access_token(
        {
            "sub": user.username,
            "role": user.role,
            "email": user.email,
            "auth_provider": user.auth_provider,
        }
    )


@router.post("/bootstrap-admin")
def bootstrap_admin(
    payload: BootstrapAdminRequest,
    db: Session = Depends(get_db),
):
    bootstrap_key = os.getenv("BOOTSTRAP_ADMIN_KEY")

    if not bootstrap_key:
        raise HTTPException(
            status_code=500,
            detail="BOOTSTRAP_ADMIN_KEY is not configured",
        )

    existing = db.query(User).filter(User.username == payload.username).first()

    if existing:
        existing.display_name = payload.display_name
        existing.email = payload.email
        existing.role = "INSYT Admin"
        existing.status = "Active"
        existing.auth_provider = "local"
        existing.password_hash = hash_password(payload.password)
        existing.workspace_access = json.dumps(["ALL"])
        existing.client_access = json.dumps(["ALL"])
        existing.project_access = json.dumps(["ALL"])
        existing.permissions = json.dumps(["ALL"])

        db.commit()
        db.refresh(existing)

        return {
            "status": "updated",
            "user": serialize_user(existing),
        }

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role="INSYT Admin",
        status="Active",
        auth_provider="local",
        password_hash=hash_password(payload.password),
        workspace_access=json.dumps(["ALL"]),
        client_access=json.dumps(["ALL"]),
        project_access=json.dumps(["ALL"]),
        launches=json.dumps([]),
        permissions=json.dumps(["ALL"]),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "created",
        "user": serialize_user(user),
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="User account is not active",
        )

    if user.auth_provider == "entra":
        raise HTTPException(
            status_code=403,
            detail="This user must sign in with Microsoft Entra.",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if user.role == "INSYT Admin":
        if not user.mfa_enabled:
            token = create_user_token(user)

            return {
                "status": "mfa_setup_required",
                "message": "INSYT Admin MFA setup is required.",
                "user": serialize_user(user),
                "access_token": token,
                "token_type": "bearer",
            }

        totp = pyotp.TOTP(user.mfa_secret or "")

        if not payload.mfa_code:
            return {
                "status": "mfa_required",
                "message": "MFA code required.",
                "user": serialize_user(user),
            }

        if not totp.verify(payload.mfa_code, valid_window=1):
            raise HTTPException(
                status_code=401,
                detail="Invalid MFA code",
            )

    token = create_user_token(user)

    return {
        "status": "success",
        "user": serialize_user(user),
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/mfa/setup")
def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "INSYT Admin":
        raise HTTPException(
            status_code=403,
            detail="MFA setup is currently required only for INSYT Admins.",
        )

    user = db.query(User).filter(User.username == current_user.username).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    secret = user.mfa_secret or pyotp.random_base32()
    user.mfa_secret = secret

    db.commit()
    db.refresh(user)

    issuer = "INSYT360"
    account_name = user.email or user.username

    otp_uri = pyotp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=issuer,
    )

    qr = qrcode.make(otp_uri)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")

    qr_data_url = (
        "data:image/png;base64,"
        + base64.b64encode(buffer.getvalue()).decode("utf-8")
    )

    return {
        "status": "success",
        "qr_code": qr_data_url,
        "manual_key": secret,
        "issuer": issuer,
        "account_name": account_name,
    }


@router.post("/mfa/confirm")
def confirm_mfa(
    payload: MfaConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "INSYT Admin":
        raise HTTPException(
            status_code=403,
            detail="Only INSYT Admins can confirm local MFA.",
        )

    user = db.query(User).filter(User.username == current_user.username).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.mfa_secret:
        raise HTTPException(
            status_code=400,
            detail="MFA setup has not been started.",
        )

    totp = pyotp.TOTP(user.mfa_secret)

    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(
            status_code=401,
            detail="Invalid MFA code",
        )

    user.mfa_enabled = True
    user.mfa_confirmed_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": "MFA enabled.",
        "user": serialize_user(user),
    }


@router.post("/mfa/disable")
def disable_mfa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "INSYT Admin":
        raise HTTPException(
            status_code=403,
            detail="Only INSYT Admins can disable local MFA.",
        )

    user = db.query(User).filter(User.username == current_user.username).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.mfa_enabled = False
    user.mfa_secret = ""
    user.mfa_confirmed_at = None
    user.mfa_backup_codes = json.dumps([])

    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": "MFA disabled.",
        "user": serialize_user(user),
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "user": serialize_user(current_user),
    }