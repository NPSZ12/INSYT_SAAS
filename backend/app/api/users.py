import json
import secrets
from typing import List
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.services.authorization import (
    ROLE_CLIENT_ADMIN,
    ROLE_INSYT_ADMIN,
    ROLE_INSYT_MANAGER,
    default_permissions_for_role,
    may_manage_role,
    normalize_role,
    require_user_scope_assignment,
    user_is_within_actor_client_scope,
    user_is_within_actor_scope,
    validate_auth_provider_for_role,
    validate_canonical_role,
    PERMISSION_INVITE_USERS,
    PERMISSION_MANAGE_PROJECT_ACCESS,
    PERMISSION_MANAGE_USERS,
    require_permission,
)
from app.services.entra_service import invite_external_user
from app.services.security import hash_password, require_admin


router = APIRouter(prefix="/api/users", tags=["Users"])

ROOT_ADMIN_USERNAME = str(
    os.getenv("INSYT_ROOT_ADMIN_USERNAME") or ""
).strip().lower()

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

def _is_root_admin(user: User) -> bool:
    if not ROOT_ADMIN_USERNAME:
        return False

    return (
        str(user.username or "").strip().lower()
        == ROOT_ADMIN_USERNAME
    )


def _require_root_admin_immutable(
    target: User,
) -> None:
    if not _is_root_admin(target):
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "The protected INSYT root administrator "
            "cannot be modified through user management."
        ),
    )

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

def _clean_string_set(values: List[str]) -> set[str]:
    return {
        str(value).strip()
        for value in values
        if str(value).strip()
    }


def _require_role_management_authority(
    actor: User,
    target_role: str,
) -> str:
    normalized_target_role = validate_canonical_role(
        target_role
    )

    if not may_manage_role(
        actor,
        normalized_target_role,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to assign or manage "
                f"the role {normalized_target_role!r}."
            ),
        )

    return normalized_target_role

def _client_names_from_scope(
    client_access: List[str],
    project_access: List[str],
) -> set[str]:
    client_names: set[str] = set()

    for value in client_access:
        raw = str(value or "").strip()

        if not raw or raw == "ALL":
            continue

        parts = raw.split("/")

        if len(parts) >= 2:
            client_names.add(
                "/".join(parts[1:]).strip()
            )
        else:
            client_names.add(raw)

    for value in project_access:
        raw = str(value or "").strip()

        if not raw or raw == "ALL":
            continue

        parts = raw.split("/")

        if len(parts) >= 3:
            client_names.add(
                parts[1].strip()
            )
        elif len(parts) == 2:
            client_names.add(
                parts[0].strip()
            )

    return {
        value
        for value in client_names
        if value
    }


def _require_single_client_binding(
    role: str,
    client_access: List[str],
    project_access: List[str],
) -> None:
    normalized_role = normalize_role(role)

    if normalized_role not in {
        ROLE_CLIENT_ADMIN,
        "Client",
    }:
        return

    if "ALL" in _clean_string_set(client_access):
        raise HTTPException(
            status_code=403,
            detail=(
                f"{normalized_role} cannot be assigned "
                "global client access."
            ),
        )

    explicit_clients = {
        str(value or "").strip()
        for value in client_access
        if str(value or "").strip()
        and str(value or "").strip() != "ALL"
    }

    if not explicit_clients:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{normalized_role} must be assigned "
                "to exactly one Client / DBA."
            ),
        )

    client_names = _client_names_from_scope(
        client_access,
        project_access,
    )

    if not client_names:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{normalized_role} must be assigned "
                "to exactly one Client / DBA."
            ),
        )

    if len(client_names) != 1:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{normalized_role} may only be assigned "
                "to one Client / DBA."
            ),
        )

def _require_safe_scope_assignment(
    actor: User,
    workspace_access: List[str],
    client_access: List[str],
    project_access: List[str],
) -> None:
    actor_role = normalize_role(
        actor.role
    )

    if actor_role == ROLE_CLIENT_ADMIN:
        if (
            "ALL" in _clean_string_set(workspace_access)
            or "ALL" in _clean_string_set(client_access)
            or "ALL" in _clean_string_set(project_access)
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Client Admin cannot assign global access."
                ),
            )

    require_user_scope_assignment(
        actor=actor,
        workspace_access=workspace_access,
        client_access=client_access,
        project_access=project_access,
    )


def _require_safe_permissions(
    actor: User,
    target_role: str,
    permissions: List[str],
) -> None:
    actor_role = normalize_role(
        actor.role
    )

    requested = _clean_string_set(
        permissions
    )

    if actor_role == ROLE_INSYT_ADMIN:
        return

    if "ALL" in requested:
        raise HTTPException(
            status_code=403,
            detail=(
                "Only INSYT Admin may assign ALL permissions."
            ),
        )

    permitted = set(
        default_permissions_for_role(
            target_role
        )
    )

    unauthorized = requested - permitted

    if unauthorized:
        raise HTTPException(
            status_code=403,
            detail=(
                "Requested permissions exceed the allowed "
                f"profile for {target_role}: "
                + ", ".join(sorted(unauthorized))
            ),
        )


def _require_target_in_actor_scope(
    actor: User,
    target: User,
) -> None:
    actor_role = normalize_role(
        actor.role
    )

    if actor_role == ROLE_INSYT_ADMIN:
        return

    if actor_role == ROLE_CLIENT_ADMIN:
        if not user_is_within_actor_client_scope(
            actor,
            target,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "User is outside your authorized client scope."
                ),
            )

        return

    if not user_is_within_actor_scope(
        actor,
        target,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "User is outside your authorized workspace, "
                "client, or project scope."
            ),
        )


def _require_client_admin_non_destructive(
    actor: User,
    action: str,
) -> None:
    if normalize_role(actor.role) != ROLE_CLIENT_ADMIN:
        return

    raise HTTPException(
        status_code=403,
        detail=(
            "Client Admin is not authorized to perform "
            f"the destructive action: {action}."
        ),
    )

def _password_hash_for_new_user(
    role: str,
    auth_provider: str,
    supplied_password: str,
) -> str:
    normalized_role = normalize_role(role)
    provider = str(auth_provider or "").strip().lower()

    if normalized_role == ROLE_INSYT_ADMIN:
        if provider != "local":
            raise HTTPException(
                status_code=400,
                detail="INSYT Admin must use local authentication.",
            )

        if not supplied_password:
            raise HTTPException(
                status_code=400,
                detail="INSYT Admin password is required.",
            )

        return hash_password(
            supplied_password
        )

    if provider != "entra":
        raise HTTPException(
            status_code=400,
            detail=(
                "Non-INSYT-Admin users must use "
                "Microsoft Entra authentication."
            ),
        )

    # UserModel.password_hash is currently non-nullable.
    # Store an unrecoverable random placeholder for Entra users.
    # It is never returned or used for Entra authentication.
    random_placeholder = secrets.token_urlsafe(48)

    return hash_password(
        random_placeholder
    )

@router.get("")
@router.get("/")
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.username.asc()).all()

    admin_role = normalize_role(
        admin.role
    )

    if admin_role == ROLE_CLIENT_ADMIN:
        users = [
            user
            for user in users
            if user_is_within_actor_client_scope(
                admin,
                user,
            )
        ]

    elif admin_role != ROLE_INSYT_ADMIN:
        users = [
            user
            for user in users
            if user_is_within_actor_scope(
                admin,
                user,
            )
        ]

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
    require_permission(
        admin,
        PERMISSION_INVITE_USERS,
    )
    username = (payload.username or "").strip()
    email = (payload.email or "").strip().lower()
    auth_provider = str(payload.auth_provider or "entra").strip().lower()

    normalized_role = _require_role_management_authority(
        admin,
        payload.role,
    )

    if normalized_role == ROLE_INSYT_ADMIN:
        auth_provider = "local"
        payload.auth_provider = "local"

    validate_auth_provider_for_role(
        normalized_role,
        auth_provider,
    )

    _require_safe_scope_assignment(
        admin,
        payload.workspace_access,
        payload.client_access,
        payload.project_access,
    )

    _require_safe_permissions(
        admin,
        normalized_role,
        payload.permissions,
    )

    _require_single_client_binding(
        normalized_role,
        payload.client_access,
        payload.project_access,
    )

    payload.role = normalized_role

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
        password_hash=_password_hash_for_new_user(
            role=payload.role,
            auth_provider=payload.auth_provider,
            supplied_password=payload.password,
        ),
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
    # update_user()
    require_permission(
        admin,
        PERMISSION_MANAGE_USERS,
    )
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

    _require_root_admin_immutable(
        user,
    )

    _require_target_in_actor_scope(
        admin,
        user,
    )

    normalized_role = _require_role_management_authority(
        admin,
        payload.role,
    )

    validate_auth_provider_for_role(
        normalized_role,
        auth_provider,
    )

    _require_safe_scope_assignment(
        admin,
        payload.workspace_access,
        payload.client_access,
        payload.project_access,
    )

    _require_safe_permissions(
        admin,
        normalized_role,
        payload.permissions,
    )

    _require_single_client_binding(
        normalized_role,
        payload.client_access,
        payload.project_access,
    )

    payload.role = normalized_role
    
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
        if normalize_role(user.role) != ROLE_INSYT_ADMIN:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Microsoft Entra users do not use "
                    "INSYT local passwords."
                ),
            )

        user.password_hash = hash_password(
            payload.password
        )

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
    # delete_user()
    require_permission(
        admin,
        PERMISSION_MANAGE_USERS,
    )
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "not_found"}

    _require_root_admin_immutable(
        user,
    )

    _require_target_in_actor_scope(
        admin,
        user,
    )

    _require_client_admin_non_destructive(
        admin,
        "delete user",
    )

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
    # reset_password()
    require_permission(
        admin,
        PERMISSION_MANAGE_USERS,
    )
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "user_not_found"}

    _require_root_admin_immutable(
        user,
    )

    _require_target_in_actor_scope(
        admin,
        user,
    )

    if normalize_role(user.role) == ROLE_INSYT_ADMIN:
        if normalize_role(admin.role) != ROLE_INSYT_ADMIN:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Only INSYT Admin may reset "
                    "an INSYT Admin password."
                ),
            )

    if str(user.auth_provider or "").strip().lower() == "entra":
        raise HTTPException(
            status_code=400,
            detail=(
                "Microsoft Entra users do not use "
                "INSYT local passwords."
            ),
        )

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
    require_permission(
        admin,
        PERMISSION_MANAGE_PROJECT_ACCESS,
    )

    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user:
        return {"status": "user_not_found"}

    _require_root_admin_immutable(
        user,
    )

    _require_target_in_actor_scope(
        admin,
        user,
    )

    actor_role = normalize_role(
        admin.role
    )

    if actor_role == ROLE_CLIENT_ADMIN:
        if not user_is_within_actor_client_scope(
            admin,
            user,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Client Admin may only manage "
                    "users within their own client."
                ),
            )

        _require_safe_scope_assignment(
            admin,
            json.loads(user.workspace_access or "[]"),
            json.loads(user.client_access or "[]"),
            [payload.project_id],
        )

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