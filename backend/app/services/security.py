import os
import json
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User


bearer_scheme = HTTPBearer(auto_error=False)


def _normalize_password(password: str) -> bytes:
    password_bytes = str(password or "").encode("utf-8")
    digest = hashlib.sha256(password_bytes).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(_normalize_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    return bcrypt.checkpw(_normalize_password(plain_password), password_hash.encode("utf-8"))


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if not JWT_SECRET_KEY:
    raise RuntimeError("Missing JWT_SECRET_KEY environment variable")


def create_access_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing authentication token")

    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")

    if not username:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user = db.query(User).filter(User.username == username).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if user.status != "Active":
        raise HTTPException(status_code=403, detail="User account is not active")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    admin_roles = {"Admin", "CDS Admin", "INSYT Admin", "Super Admin"}

    if current_user.role not in admin_roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user


def safe_json_list(value: str):
    try:
        return json.loads(value or "[]")
    except Exception:
        return []