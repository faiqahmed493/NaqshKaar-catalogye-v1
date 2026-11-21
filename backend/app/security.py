"""Password hashing (scrypt, stdlib), JWT access tokens, API keys and signed file URLs."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid

import jwt

from .config import get_settings

settings = get_settings()

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        test = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(test, _unb64(dk))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + settings.access_token_minutes * 60,
               "typ": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    data = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return data


# --------------------------------------------------------------------------- API keys
API_KEY_PREFIX = "nqk"


def generate_api_key() -> tuple[str, str, str]:
    """Return (full key shown once, lookup prefix, sha256 hash to store)."""
    prefix = secrets.token_hex(5)
    full = f"{API_KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    return full, prefix, hash_api_key(full)


def hash_api_key(full: str) -> str:
    return hashlib.sha256(full.encode()).hexdigest()


def api_key_prefix(full: str) -> str | None:
    parts = full.split("_", 2)
    if len(parts) != 3 or parts[0] != API_KEY_PREFIX:
        return None
    return parts[1]


# --------------------------------------------------------------------------- signed file URLs
def sign_file(file_id: uuid.UUID | str, expires_at: int) -> str:
    msg = f"{file_id}:{expires_at}".encode()
    return _b64(hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).digest()[:24])


def file_url(file_id: uuid.UUID | str | None, ttl: int | None = None) -> str | None:
    """Path-relative signed URL. The UI uses it as is; remote workers prefix their STUDIO_URL."""
    if file_id is None:
        return None
    exp = int(time.time()) + (ttl or settings.file_url_ttl_seconds)
    # Round expiry to the hour boundary so the same file keeps one URL for a while (browser caching).
    exp = exp - (exp % 3600) + 3600
    return f"/api/files/{file_id}?exp={exp}&sig={sign_file(file_id, exp)}"


def verify_file_signature(file_id: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sign_file(file_id, exp), sig)
