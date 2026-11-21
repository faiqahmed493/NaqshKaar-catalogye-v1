from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import EDITORS, Principal, any_user, require_roles
from ..models import Category, GenerationEngine, Retailer
from ..schemas import RetailerIn, RetailerPatch
from ..services.audit import audit
from ..services.jobs import online_workers

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/retailers")
def list_retailers(db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    return [ser.retailer(r) for r in db.scalars(select(Retailer).order_by(Retailer.name))]


@router.post("/retailers", status_code=201)
def create_retailer(body: RetailerIn, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    if db.scalar(select(Retailer).where(Retailer.slug == body.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Retailer slug '{body.slug}' exists")
    r = Retailer(**body.model_dump())
    db.add(r)
    db.flush()
    audit(db, p, "retailer.created", "retailer", r.id)
    db.commit()
    return ser.retailer(r)


@router.patch("/retailers/{retailer_id}")
def update_retailer(retailer_id: uuid.UUID, body: RetailerPatch, db: Session = Depends(get_db),
                    p: Principal = Depends(require_roles(*EDITORS))):
    r = db.get(Retailer, retailer_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Retailer not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    audit(db, p, "retailer.updated", "retailer", r.id)
    db.commit()
    return ser.retailer(r)


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    cats = list(db.scalars(select(Category).order_by(Category.sort_order, Category.name)))
    return [ser.category(c) for c in cats]


@router.get("/engines")
def list_engines(db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    workers = online_workers(db)
    counts: dict[str, int] = {}
    for w in workers:
        for e in w.engines:
            counts[e] = counts.get(e, 0) + 1
    engines = db.scalars(select(GenerationEngine).order_by(GenerationEngine.sort_order))
    return {"engines": [ser.engine(e, counts.get(e.code, 0)) for e in engines],
            "workers": [{"id": w.id, "engines": w.engines, "hostname": w.hostname, "gpu_name": w.gpu_name,
                         "gpu_vram_gb": w.gpu_vram_gb, "version": w.version, "last_seen_at": ser.iso(w.last_seen_at)}
                        for w in workers]}


class EnginePatch(BaseModel):
    is_enabled: bool | None = None
    default_params: dict | None = None


@router.patch("/engines/{code}")
def update_engine(code: str, body: EnginePatch, db: Session = Depends(get_db), p: Principal = Depends(require_roles())):
    e = db.get(GenerationEngine, code)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Engine not found")
    if body.is_enabled is not None:
        e.is_enabled = body.is_enabled
    if body.default_params is not None:
        e.default_params = body.default_params
    audit(db, p, "engine.updated", "engine", code, body.model_dump(exclude_none=True))
    db.commit()
    return ser.engine(e)
