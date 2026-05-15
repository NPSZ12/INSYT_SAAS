import os

from app.services.security import hash_password
import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.security import verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    
class BootstrapAdminRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str

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
        existing.role = "CDS Admin"
        existing.status = "Active"
        existing.password_hash = hash_password(payload.password)

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
        role="CDS Admin",
        status="Active",
        password_hash=hash_password(payload.password),
        project_access="[]",
        launches="[]",
        permissions="[]",
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
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if user.status != "Active":
        raise HTTPException(status_code=403, detail="User account is not active")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(
        {
            "sub": user.username,
            "role": user.role,
            "email": user.email,
        }
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