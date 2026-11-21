"""Request authentication: user JWTs for the web UI, API keys for collectors, workers and the planner."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .enums import UserRole
from .models import ApiKey, AppUser
from .security import api_key_prefix, decode_access_token, hash_api_key

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    user: AppUser | None = None
    api_key: ApiKey | None = None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def api_key_id(self) -> uuid.UUID | None:
        return self.api_key.id if self.api_key else None

    @property
    def label(self) -> str:
        if self.user:
            return self.user.email
        return f"api-key:{self.api_key.name}" if self.api_key else "anonymous"


def _unauthorised(msg: str = "Sign in required") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def _user_from_token(token: str, db: Session) -> AppUser:
    try:
        data = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorised("Session expired; sign in again") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorised("Invalid session token") from exc
    user = db.get(AppUser, uuid.UUID(data["sub"]))
    if not user or not user.is_active:
        raise _unauthorised("Account not found or disabled")
    return user


def _api_key_from_value(value: str, db: Session) -> ApiKey | None:
    prefix = api_key_prefix(value)
    if not prefix:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if not key or key.revoked_at is not None or key.key_hash != hash_api_key(value):
        return None
    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                     db: Session = Depends(get_db)) -> AppUser:
    if not creds or creds.scheme.lower() != "bearer":
        raise _unauthorised()
    if creds.credentials.startswith("nqk_"):
        raise _unauthorised("This endpoint needs a user session, not an API key")
    return _user_from_token(creds.credentials, db)


def require_roles(*roles: UserRole):
    allowed = {r.value for r in roles} | {UserRole.admin.value}

    def dep(user: AppUser = Depends(get_current_user)) -> Principal:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Your role ({user.role}) cannot do this. Needed: {', '.join(sorted(allowed))}")
        return Principal(user=user)
    return dep


def any_user(user: AppUser = Depends(get_current_user)) -> Principal:
    return Principal(user=user)


def require_api_key(scope: str):
    def dep(x_api_key: str | None = Header(default=None),
            creds: HTTPAuthorizationCredentials | None = Depends(bearer),
            db: Session = Depends(get_db)) -> Principal:
        value = x_api_key or (creds.credentials if creds and creds.credentials.startswith("nqk_") else None)
        if not value:
            raise _unauthorised("API key required (X-API-Key header)")
        key = _api_key_from_value(value, db)
        if not key:
            raise _unauthorised("Invalid or revoked API key")
        if scope not in key.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key lacks the '{scope}' scope")
        return Principal(api_key=key)
    return dep


def user_or_api_key(scope: str, *roles: UserRole):
    """Accept a signed-in user with one of ``roles`` (any role if empty) or an API key with ``scope``."""
    allowed = {r.value for r in roles} | {UserRole.admin.value} if roles else None

    def dep(x_api_key: str | None = Header(default=None),
            creds: HTTPAuthorizationCredentials | None = Depends(bearer),
            db: Session = Depends(get_db)) -> Principal:
        value = x_api_key or (creds.credentials if creds else None)
        if not value:
            raise _unauthorised()
        if value.startswith("nqk_"):
            key = _api_key_from_value(value, db)
            if not key:
                raise _unauthorised("Invalid or revoked API key")
            if scope not in key.scopes:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key lacks the '{scope}' scope")
            return Principal(api_key=key)
        user = _user_from_token(value, db)
        if allowed and user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({user.role}) cannot do this")
        return Principal(user=user)
    return dep


# Role groups used across routers
EDITORS = (UserRole.curator,)
GENERATORS = (UserRole.curator, UserRole.asset_reviewer)
ASSET_REVIEWERS = (UserRole.asset_reviewer, UserRole.curator)
