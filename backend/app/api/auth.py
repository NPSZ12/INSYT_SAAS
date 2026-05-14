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