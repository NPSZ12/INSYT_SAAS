import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.services.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )
    
    print("LOGIN ATTEMPT:", payload.username)
    print("USER FOUND:", bool(user))

    if user:
        print("USER STATUS:", user.status)
        print("HASH START:", user.password_hash[:20])

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

    print("PASSWORD LENGTH:", len(payload.password))

    if not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    return {
        "status": "success",
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "project_access": json.loads(user.project_access or "[]"),
            "launches": json.loads(user.launches or "[]"),
            "permissions": json.loads(user.permissions or "[]"),
        },
        "token": "temporary-dev-token",
    }