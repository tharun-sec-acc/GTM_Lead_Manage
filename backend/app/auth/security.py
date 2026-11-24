import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with salt rounds=12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against the stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
    except Exception:
        return False


def hash_token(token: str) -> str:
    """Generate SHA-256 hash of a raw token for database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC, ensuring timezone awareness."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    is_superadmin: bool = False,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """
    Create a signed JWT access token.
    Returns: (token_str, jti, expire_datetime)
    """
    jti = secrets.token_hex(16)
    delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = datetime.now(timezone.utc) + delta
    claims: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "is_superadmin": is_superadmin,
        "jti": jti,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expire


def create_refresh_token(
    user_id: str,
    org_id: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """
    Create a signed JWT refresh token.
    Returns: (token_str, jti, expire_datetime)
    """
    jti = secrets.token_hex(16)
    delta = expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days)
    expire = datetime.now(timezone.utc) + delta
    claims: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "jti": jti,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expire


def decode_jwt_token(token: str) -> dict[str, Any]:
    """Decode and validate claims in a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti", "type"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}")


def get_oauth_cipher() -> Fernet:
    """Return Fernet cipher for encrypting OAuth refresh/access tokens."""
    # Use google_token_encryption_key or microsoft_token_encryption_key or derive
    key = (
        getattr(settings, "google_token_encryption_key", "")
        or getattr(settings, "microsoft_token_encryption_key", "")
    )
    if not key:
        # Fallback to key derived from jwt_secret_key
        derived = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
        import base64
        key = base64.urlsafe_b64encode(derived).decode("ascii")
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_token(token_str: str) -> bytes:
    """Encrypt a sensitive token string into encrypted bytes for database storage."""
    return get_oauth_cipher().encrypt(token_str.encode("utf-8"))


def decrypt_token(token_bytes: bytes) -> str:
    """Decrypt encrypted token bytes from database back into plaintext."""
    return get_oauth_cipher().decrypt(token_bytes).decode("utf-8")
