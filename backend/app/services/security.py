import base64
import hashlib
import bcrypt


def _normalize_password(password: str) -> bytes:
    """
    bcrypt has a 72-byte limit.
    We SHA-256 pre-hash first, then base64 encode.
    This avoids the 72-byte bcrypt limit safely.
    """
    password_bytes = str(password or "").encode("utf-8")
    digest = hashlib.sha256(password_bytes).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")

    normalized = _normalize_password(password)
    hashed = bcrypt.hashpw(normalized, bcrypt.gensalt())

    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False

    normalized = _normalize_password(plain_password)

    return bcrypt.checkpw(
        normalized,
        password_hash.encode("utf-8"),
    )