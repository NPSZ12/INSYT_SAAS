import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.entra_service import invite_external_user
from app.services.security import hash_password, require_admin


router = APIRouter(prefix="/api/users", tags=["Users"])

DUPLICATE_USERNAME_MESSAGE = (
    "Duplicate Username Detected, Contact an INSYT Admin for Assistance."
)

DUPLICATE_EMAIL_MESSAGE = (
    "Duplicate Email Detected, Contact an INSYT Admin for Assistance."
)


class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    auth_provider: str = "entra"
    password: str = ""
    workspace_access: List[str] = Field(default_factory=list)
    client_access: List[str] = Field(default_factory=list)
    project_access: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    auth_provider: str = "entra"
    status: str = "Active"
    password: str = ""
    workspace_access: List[str] = Field(default_factory=list)
    client_access: List[str] = Field(default_factory=list)
    project_access: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class UserDeleteRequest(BaseModel):
    username: str


class PasswordResetRequest(BaseModel):
    username: str
    new_password: str


class ProjectAccessRequest(BaseModel):
    username: str
    project_id: str
    allowed: bool


def serialize_user(user: User):
    return {
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "auth_provider": user.auth_provider,
        "workspace_access": json.loads(user.workspace_access or "[]"),
        "client_access": json.loads(user.client_access or "[]"),
        "project_access": json.loads(user.project_access or "[]"),
        "permissions": json.loads(user.permissions or "[]"),
    }

@router.get("")
@router.get("/")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.username.asc()).all()

    return {
        "status": "success",
        "users": [serialize_user(user) for user in users],
    }


@router.post("/create")
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    username = (payload.username or "").strip()
    email = (payload.email or "").strip().lower()
    auth_provider = str(payload.auth_provider or "entra").strip().lower()

    existing_username_user = (
        db.query(User)
        .filter(User.username.ilike(username))
        .first()
    )

    if existing_username_user:
        write_audit_log(
            db=db,
            action="USER_CREATE_FAILED",
            actor=admin,
            request=request,
            target_type="user",
            target_id=username,
            details={
                "reason": "duplicate_username_detected",
                "username": username,
                "existing_username": existing_username_user.username,
            },
        )

        raise HTTPException(
            status_code=409,
            detail=DUPLICATE_USERNAME_MESSAGE,
        )

    if email:
        existing_email_user = (
            db.query(User)
            .filter(User.email.ilike(email))
            .first()
        )

        if existing_email_user:
            write_audit_log(
                db=db,
                action="USER_CREATE_FAILED",
                actor=admin,
                request=request,
                target_type="user",
                target_id=username,
                details={
                    "reason": "duplicate_email_detected",
                    "email": email,
                    "existing_username": existing_email_user.username,
                },
            )

            raise HTTPException(
                status_code=409,
                detail=DUPLICATE_EMAIL_MESSAGE,
            )

    payload.username = username
    payload.email = email
    payload.auth_provider = auth_provider
        
    email = (payload.email or "").strip().lower()

    if email:
        existing_email_user = (
            db.query(User)
            .filter(User.email.ilike(email))
            .first()
        )

        if existing_email_user:
            write_audit_log(
                db=db,
                action="USER_CREATE_FAILED",
                actor=admin,
                request=request,
                target_type="user",
                target_id=payload.username,
                details={
                    "reason": "duplicate_email_detected",
                    "email": email,
                    "existing_username": existing_email_user.username,
                },
            )

            raise HTTPException(
                status_code=409,
                detail=DUPLICATE_EMAIL_MESSAGE,
            )

    payload.email = email
    payload.auth_provider = str(payload.auth_provider or "entra").strip().lower()

    if (
        payload.role == "INSYT Admin"
        and admin.role != "INSYT Admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Only an INSYT Admin may assign INSYT Admin access.",
        )

    if payload.role == "INSYT Admin":
        payload.auth_provider = "local"

        payload.workspace_access = ["ALL"]
        payload.client_access = ["ALL"]
        payload.project_access = ["ALL"]
        payload.permissions = ["ALL"]

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        auth_provider=payload.auth_provider,
        status="Active",
        password_hash=hash_password(payload.password),
        workspace_access=json.dumps(payload.workspace_access),
        client_access=json.dumps(payload.client_access),
        project_access=json.dumps(payload.project_access),
        permissions=json.dumps(payload.permissions),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    write_audit_log(
        db=db,
        action="USER_CREATED",
        actor=admin,
        request=request,
        target_type="user",
        target_id=user.username,
        details={
            "email": user.email,
            "role": user.role,
            "auth_provider": user.auth_provider,
        },
    )

    if payload.auth_provider == "entra":
        try:
            invite_external_user(
                payload.email,
                payload.display_name,
            )

            write_audit_log(
                db=db,
                action="ENTRA_INVITATION_SENT",
                actor=admin,
                request=request,
                target_type="user",
                target_id=user.username,
                details={
                    "email": user.email,
                    "display_name": user.display_name,
                },
            )

        except Exception as error:
            print(
                f"Unable to invite Entra user: {error}"
            )

            write_audit_log(
                db=db,
                action="ENTRA_INVITATION_FAILED",
                actor=admin,
                request=request,
                target_type="user",
                target_id=user.username,
                details={
                    "email": user.email,
                    "error": str(error),
                },
            )

    return {
        "status": "created",
        "user": serialize_user(user),
    }


@router.post("/update")
def update_user(
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    username = (payload.username or "").strip()
    email = (payload.email or "").strip().lower()
    auth_provider = str(payload.auth_provider or "entra").strip().lower()

    user = (
        db.query(User)
        .filter(User.username.ilike(username))
        .first()
    )

    if not user:
        return {"status": "not_found"}
    
    if email:
        existing_email_user = (
            db.query(User)
            .filter(User.email.ilike(email))
            .filter(User.id != user.id)
            .first()
        )

        if existing_email_user:
            write_audit_log(
                db=db,
                action="USER_UPDATE_FAILED",
                actor=admin,
                request=request,
                target_type="user",
                target_id=user.username,
                details={
                    "reason": "duplicate_email_detected",
                    "email": email,
                    "existing_username": existing_email_user.username,
                },
            )

            raise HTTPException(
                status_code=409,
                detail=DUPLICATE_EMAIL_MESSAGE,
            )

    payload.username = user.username
    payload.email = email
    payload.auth_provider = auth_provider
    
    email = (payload.email or "").strip().lower()

    if email:
        existing_email_user = (
            db.query(User)
            .filter(User.email.ilike(email))
            .filter(User.username != payload.username)
            .first()
        )

        if existing_email_user:
            write_audit_log(
                db=db,
                action="USER_UPDATE_FAILED",
                actor=admin,
                request=request,
                target_type="user",
                target_id=payload.username,
                details={
                    "reason": "duplicate_email_detected",
                    "email": email,
                    "existing_username": existing_email_user.username,
                },
            )

            raise HTTPException(
                status_code=409,
                detail=DUPLICATE_EMAIL_MESSAGE,
            )

    payload.email = email
    payload.auth_provider = str(payload.auth_provider or "entra").strip().lower()

    if (
        payload.role == "INSYT Admin"
        and admin.role != "INSYT Admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Only an INSYT Admin may assign INSYT Admin access.",
        )

    if payload.role == "INSYT Admin":
        payload.auth_provider = "local"

        payload.workspace_access = ["ALL"]
        payload.client_access = ["ALL"]
        payload.project_access = ["ALL"]
        payload.permissions = ["ALL"]

    previous = {
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "auth_provider": user.auth_provider,
        "status": user.status,
        "workspace_access": json.loads(user.workspace_access or "[]"),
        "client_access": json.loads(user.client_access or "[]"),
        "project_access": json.loads(user.project_access or "[]"),
        "permissions": json.loads(user.permissions or "[]"),
    }

    user.display_name = payload.display_name
    user.email = payload.email
    user.role = payload.role
    user.auth_provider = payload.auth_provider
    user.status = payload.status

    user.workspace_access = json.dumps(payload.workspace_access)
    user.client_access = json.dumps(payload.client_access)
    user.project_access = json.dumps(payload.project_access)
    user.permissions = json.dumps(payload.permissions)

    if payload.password:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)

    write_audit_log(
        db=db,
        action="USER_UPDATED",
        actor=admin,
        request=request,
        target_type="user",
        target_id=user.username,
        details={
            "previous": previous,
            "current": {
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "auth_provider": user.auth_provider,
                "status": user.status,
                "workspace_access": json.loads(user.workspace_access or "[]"),
                "client_access": json.loads(user.client_access or "[]"),
                "project_access": json.loads(user.project_access or "[]"),
                "permissions": json.loads(user.permissions or "[]"),
            },
        },
    )

    return {
        "status": "updated",
        "user": serialize_user(user),
    }


@router.post("/delete")
def delete_user(
    payload: UserDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "not_found"}

    if user.role == "INSYT Admin":
        admin_count = (
            db.query(User)
            .filter(User.role == "INSYT Admin")
            .count()
        )

        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="At least one INSYT Admin must remain.",
            )

    deleted_snapshot = {
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "auth_provider": user.auth_provider,
        "status": user.status,
    }

    db.delete(user)
    db.commit()

    write_audit_log(
        db=db,
        action="USER_DELETED",
        actor=admin,
        request=request,
        target_type="user",
        target_id=payload.username,
        details=deleted_snapshot,
    )

    return {
        "status": "deleted",
        "user": payload.username,
    }


@router.post("/reset-password")
def reset_password(
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "user_not_found"}

    user.password_hash = hash_password(payload.new_password)

    db.commit()

    return {
        "status": "password_reset",
        "username": payload.username,
    }


@router.post("/project-access")
def update_project_access(
    payload: ProjectAccessRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "user_not_found"}

    access = json.loads(user.project_access or "[]")

    if payload.allowed and payload.project_id not in access:
        access.append(payload.project_id)

    if not payload.allowed and payload.project_id in access:
        access.remove(payload.project_id)

    user.project_access = json.dumps(access)

    db.commit()
    db.refresh(user)

    return {
        "status": "updated",
        "username": payload.username,
        "project_access": access,
    }