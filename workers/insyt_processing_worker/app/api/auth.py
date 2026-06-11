import base64
import io
import json
import os
from datetime import datetime
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from urllib.parse import urlencode
from app.services.audit_service import write_audit_log

import requests

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
    
class EntraLoginRequest(BaseModel):
    email: str


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

def entra_authority():
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0"


def entra_redirect_uri():
    return os.getenv(
        "ENTRA_REDIRECT_URI",
        "http://localhost:3000/auth/entra/callback",
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
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user:
        write_audit_log(
            db=db,
            action="LOGIN_FAILED",
            request=request,
            target_type="user",
            target_id=payload.username,
            details={
                "reason": "user_not_found",
            },
        )

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
        write_audit_log(
            db=db,
            action="LOGIN_FAILED",
            actor=user,
            request=request,
            target_type="user",
            target_id=user.username,
            details={
                "reason": "bad_password",
            },
        )

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

    write_audit_log(
        db=db,
        action="LOGIN_SUCCESS",
        actor=user,
        request=request,
        target_type="user",
        target_id=user.username,
        details={
            "provider": "local",
        },
    )

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

@router.post("/entra-login")
def entra_login(
    payload: EntraLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = (payload.email or "").strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Missing Entra email.",
        )

    user = (
        db.query(User)
        .filter(User.email.ilike(email))
        .first()
    )

    if not user:
        write_audit_log(
            db=db,
            action="ENTRA_LOGIN_FAILED",
            request=request,
            target_type="user",
            target_id=email,
            details={
                "reason": "user_not_found",
                "email": email,
            },
        )

        raise HTTPException(
            status_code=403,
            detail=(
                "This email address has not been provisioned in INSYT. "
                "Please contact your INSYT administrator."
            ),
        )

    if user.status != "Active":
        write_audit_log(
            db=db,
            action="ENTRA_LOGIN_FAILED",
            actor=user,
            request=request,
            target_type="user",
            target_id=user.username,
            details={
                "reason": "inactive_user",
                "email": email,
            },
        )

        raise HTTPException(
            status_code=403,
            detail="User account is not active.",
        )

    if user.role == "INSYT Admin":
        write_audit_log(
            db=db,
            action="ENTRA_LOGIN_FAILED",
            actor=user,
            request=request,
            target_type="user",
            target_id=user.username,
            details={
                "reason": "admin_must_use_local_mfa",
                "email": email,
            },
        )

        raise HTTPException(
            status_code=403,
            detail="INSYT Admins must use local INSYT login with MFA.",
        )

    if user.auth_provider != "entra":
        write_audit_log(
            db=db,
            action="ENTRA_LOGIN_FAILED",
            actor=user,
            request=request,
            target_type="user",
            target_id=user.username,
            details={
                "reason": "user_not_configured_for_entra",
                "email": email,
                "auth_provider": user.auth_provider,
            },
        )

        raise HTTPException(
            status_code=403,
            detail="This user is not configured for Microsoft Entra login.",
        )

    token = create_user_token(user)

    write_audit_log(
        db=db,
        action="ENTRA_LOGIN_SUCCESS",
        actor=user,
        request=request,
        target_type="user",
        target_id=user.username,
        details={
            "provider": "entra",
            "email": email,
        },
    )

    return {
        "status": "success",
        "user": serialize_user(user),
        "access_token": token,
        "token": token,
        "token_type": "bearer",
    }

@router.get("/entra/start")
def entra_start():
    client_id = os.getenv("ENTRA_CLIENT_ID")

    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="ENTRA_CLIENT_ID is not configured.",
        )

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": entra_redirect_uri(),
        "response_mode": "query",
        "scope": "openid profile email User.Read",
        "prompt": "select_account",
    }

    return {
        "status": "success",
        "auth_url": f"{entra_authority()}/authorize?{urlencode(params)}",
    }


@router.post("/entra/callback")
def entra_callback(
    payload: dict,
    db: Session = Depends(get_db),
):
    code = payload.get("code")

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Missing Entra authorization code.",
        )

    token_response = requests.post(
        f"{entra_authority()}/token",
        data={
            "client_id": os.getenv("ENTRA_CLIENT_ID"),
            "client_secret": os.getenv("ENTRA_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": entra_redirect_uri(),
            "scope": "openid profile email User.Read",
        },
        timeout=20,
    )

    if token_response.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail="Unable to exchange Entra authorization code.",
        )

    token_data = token_response.json()
    

    userinfo_response = requests.get(
        "https://graph.microsoft.com/oidc/userinfo",
        headers={
            "Authorization": f"Bearer {token_data.get('access_token')}",
        },
        timeout=20,
    )

    if userinfo_response.status_code >= 400:
        raise HTTPException(
            status_code=401,
            detail="Unable to read Entra user profile.",
        )

    profile = userinfo_response.json()

    email = (
        profile.get("email")
        or profile.get("preferred_username")
        or profile.get("upn")
        or ""
    ).lower()

    display_name = profile.get("name") or email

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Entra profile did not include an email.",
        )

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=403,
            detail=(
                "This email address has not been provisioned in INSYT. "
                "Please contact your INSYT administrator."
            ),
        )

    if user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="User account is not active.",
        )

    if user.role == "INSYT Admin":
        raise HTTPException(
            status_code=403,
            detail="INSYT Admins must use local INSYT login with MFA.",
        )

    if user.auth_provider != "entra":
        raise HTTPException(
            status_code=403,
            detail="This user is not configured for Microsoft Entra login.",
        )

    token = create_user_token(user)

    write_audit_log(
        db=db,
        action="ENTRA_LOGIN_SUCCESS",
        actor=user,
        target_type="user",
        target_id=user.username,
        details={
            "provider": "entra",
        },
    )

    return {
        "status": "success",
        "user": serialize_user(user),
        "access_token": token,
        "token_type": "bearer",
    }

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "user": serialize_user(current_user),
    }