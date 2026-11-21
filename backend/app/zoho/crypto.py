import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import settings


def _get_encryption_key() -> bytes:
    key_candidate = (
        getattr(settings, "zoho_token_encryption_key", "")
        or getattr(settings, "google_token_encryption_key", "")
    )
    if key_candidate:
        try:
            raw = key_candidate.strip().encode("ascii")
            # Verify valid 32-byte url-safe base64
            Fernet(raw)
            return raw
        except Exception:
            pass

    # Deterministic fallback derived from database url
    seed = (settings.database_url or "zoho-default-secret-seed").encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(digest)


def get_cipher() -> Fernet:
    return Fernet(_get_encryption_key())


def encrypt_token(token: str | bytes | None) -> bytes:
    if not token:
        return b""
    if isinstance(token, str):
        token = token.encode("utf-8")
    return get_cipher().encrypt(token)


def decrypt_token(encrypted: bytes | None) -> str:
    if not encrypted:
        return ""
    try:
        return get_cipher().decrypt(encrypted).decode("utf-8")
    except Exception as exc:
        raise RuntimeError("Zoho token cannot be decrypted; check the encryption key.") from exc
