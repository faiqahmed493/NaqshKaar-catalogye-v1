from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import Principal, any_user, require_roles
from ..models import ApiKey, AppUser
from ..schemas import ApiKeyCreate, LoginIn, UserCreate, UserUpdate
from ..security import create_access_token, generate_api_key, hash_password, verify_password
from ..services.audit import audit

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(AppUser).where(AppUser.email == body.email.strip()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer", "user": ser.user(user)}


@router.get("/auth/me")
def me(p: Principal = Depends(any_user)):
    return ser.user(p.user)


# --------------------------------------------------------------------------- users (admin)
@router.get("/users")
def list_users(db: Session = Depends(get_db), _: Principal = Depends(require_roles())):
    return [ser.user(u) for u in db.scalars(select(AppUser).order_by(AppUser.created_at))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), p: Principal = Depends(require_roles())):
    if db.scalar(select(AppUser).where(AppUser.email == body.email.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email exists")
    u = AppUser(email=body.email.strip(), display_name=body.display_name, password_hash=hash_password(body.password),
                role=body.role)
    db.add(u)
    db.flush()
    audit(db, p, "user.created", "user", u.id, {"role": u.role})
    db.commit()
    return ser.user(u)


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdate, db: Session = Depends(get_db),
                p: Principal = Depends(require_roles())):
    u = db.get(AppUser, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.id == p.user_id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot demote or disable yourself")
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password:
        u.password_hash = hash_password(body.password)
    audit(db, p, "user.updated", "user", u.id, body.model_dump(exclude={"password"}, exclude_none=True))
    db.commit()
    return ser.user(u)


# --------------------------------------------------------------------------- API keys (admin)
@router.get("/api-keys")
def list_keys(db: Session = Depends(get_db), _: Principal = Depends(require_roles())):
    keys = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return [{"id": str(k.id), "name": k.name, "prefix": k.prefix, "scopes": k.scopes,
             "created_at": ser.iso(k.created_at), "last_used_at": ser.iso(k.last_used_at),
             "revoked_at": ser.iso(k.revoked_at)} for k in keys]


@router.post("/api-keys", status_code=201)
def create_key(body: ApiKeyCreate, db: Session = Depends(get_db), p: Principal = Depends(require_roles())):
    full, prefix, digest = generate_api_key()
    k = ApiKey(name=body.name, prefix=prefix, key_hash=digest, scopes=sorted(set(body.scopes)), created_by=p.user_id)
    db.add(k)
    db.flush()
    audit(db, p, "api_key.created", "api_key", k.id, {"scopes": k.scopes})
    db.commit()
    return {"id": str(k.id), "name": k.name, "scopes": k.scopes, "key": full,
            "note": "Copy this key now. Only a hash is stored, so it cannot be shown again."}


@router.post("/api-keys/{key_id}/revoke")
def revoke_key(key_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles())):
    k = db.get(ApiKey, key_id)
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Key not found")
    k.revoked_at = k.revoked_at or datetime.now(timezone.utc)
    audit(db, p, "api_key.revoked", "api_key", k.id)
    db.commit()
    return {"ok": True}
