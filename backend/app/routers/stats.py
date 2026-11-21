from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import Principal, any_user
from ..models import Asset3D, AuditLog, GenerationJob, Product, ProductVariant, Retailer

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    variants = dict(db.execute(select(ProductVariant.status, func.count()).group_by(ProductVariant.status)).all())
    assets = dict(db.execute(select(Asset3D.status, func.count()).group_by(Asset3D.status)).all())
    jobs = dict(db.execute(select(GenerationJob.status, func.count()).group_by(GenerationJob.status)).all())
    ready = db.scalar(text("SELECT count(*) FROM v_catalogue_variant WHERE eligible AND asset_ready"))
    by_group = [dict(r._mapping) for r in db.execute(text(
        "SELECT coalesce(product_group::text, 'uncategorised') AS product_group, count(*) AS variants, "
        "count(*) FILTER (WHERE eligible) AS eligible, count(*) FILTER (WHERE eligible AND asset_ready) AS ready "
        "FROM v_catalogue_variant GROUP BY 1 ORDER BY 1"))]
    return {"products": db.scalar(select(func.count()).select_from(Product)),
            "retailers": db.scalar(select(func.count()).select_from(Retailer)),
            "variants_by_status": variants, "assets_by_status": assets, "jobs_by_status": jobs,
            "eligible_and_asset_ready": ready, "by_group": by_group}


@router.get("/audit")
def audit_log(entity_type: str | None = None, entity_id: str | None = None, limit: int = Query(100, le=500),
              db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit))
    return [{"id": a.id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id,
             "details": a.details, "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
             "actor_api_key_id": str(a.actor_api_key_id) if a.actor_api_key_id else None,
             "created_at": ser.iso(a.created_at)} for a in rows]
