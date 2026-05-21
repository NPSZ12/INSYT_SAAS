import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.security import hash_password, require_admin

router = APIRouter(prefix="/api/users", tags=["Users"])


class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    password: str
    project_access: List[str] = Field(default_factory=list)
    launches: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    role: str
    status: str = "Active"
    password: str = ""
    project_access: List[str] = Field(default_factory=list)
    launches: List[str] = Field(default_factory=list)
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
        "project_access": json.loads(user.project_access or "[]"),
        "launches": json.loads(user.launches or "[]"),
        "permissions": json.loads(user.permissions or "[]"),
    }


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
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == payload.username).first()

    if existing:
        return {
            "status": "duplicate_user",
            "message": "A user with this username already exists.",
        }

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        status="Active",
        password_hash=hash_password(payload.password),
        project_access=json.dumps(payload.project_access),
        launches=json.dumps(payload.launches),
        permissions=json.dumps(payload.permissions),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "created",
        "user": serialize_user(user),
    }


@router.post("/update")
def update_user(
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user:
        return {"status": "not_found"}

    user.display_name = payload.display_name
    user.email = payload.email
    user.role = payload.role
    user.status = payload.status
    user.project_access = json.dumps(payload.project_access)
    user.launches = json.dumps(payload.launches)
    user.permissions = json.dumps(payload.permissions)

    if payload.password:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)

    return {
        "status": "updated",
        "user": serialize_user(user),
    }


@router.post("/delete")
def delete_user(
    payload: UserDeleteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user:
        return {"status": "not_found"}

    db.delete(user)
    db.commit()

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
    user = db.query(User).filter(User.username == payload.username).first()

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
    user = db.query(User).filter(User.username == payload.username).first()

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