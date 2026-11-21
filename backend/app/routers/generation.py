from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import ASSET_REVIEWERS, GENERATORS, Principal, any_user, require_roles
from ..models import GenerationJob, Product, ProductVariant
from ..schemas import AssetReviewIn, GenerationRequest, ReprocessIn
from ..services import catalogue as cat
from ..services import jobs as jobsvc
from ..services.assets import (VISUAL_CHECKLIST, get_asset_or_404, reprocess, review_asset, save_preview,
                               select_asset, upload_asset)
from ..services.audit import audit

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/variants/{variant_id}/generation-jobs", status_code=201)
def create_generation_jobs(variant_id: uuid.UUID, body: GenerationRequest, db: Session = Depends(get_db),
                           p: Principal = Depends(require_roles(*GENERATORS))):
    v = cat.get_variant_or_404(db, variant_id)
    jobs = jobsvc.create_jobs(db, v, body.engine_codes, body.image_ids, body.params, body.priority, p)
    db.commit()
    return [ser.job(j) for j in jobs]


@router.get("/jobs")
def list_jobs(status_: str | None = Query(default=None, alias="status"), engine: str | None = None,
              variant_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200),
              db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    stmt = select(GenerationJob)
    if status_:
        stmt = stmt.where(GenerationJob.status.in_(status_.split(",")))
    if engine:
        stmt = stmt.where(GenerationJob.engine_code == engine)
    if variant_id:
        stmt = stmt.where(GenerationJob.variant_id == variant_id)
    jobs = list(db.scalars(stmt.order_by(GenerationJob.created_at.desc()).limit(limit)))
    names = {}
    if jobs:
        rows = db.execute(select(ProductVariant.id, Product.name, ProductVariant.variant_label)
                          .join(Product, Product.id == ProductVariant.product_id)
                          .where(ProductVariant.id.in_({j.variant_id for j in jobs})))
        names = {r[0]: {"product_name": r[1], "variant_label": r[2]} for r in rows}
    counts = dict(db.execute(select(GenerationJob.status, func.count()).group_by(GenerationJob.status)).all())
    return {"items": [{**ser.job(j), **names.get(j.variant_id, {})} for j in jobs], "counts": counts}


def _job_or_404(db: Session, job_id: uuid.UUID) -> GenerationJob:
    j = db.get(GenerationJob, job_id)
    if not j:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return j


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    return ser.job(_job_or_404(db, job_id), include_log=True)


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*GENERATORS))):
    j = _job_or_404(db, job_id)
    jobsvc.cancel_job(db, j, p)
    db.commit()
    return ser.job(j)


@router.post("/jobs/{job_id}/retry", status_code=201)
def retry(job_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*GENERATORS))):
    new = jobsvc.retry_job(db, _job_or_404(db, job_id), p)
    db.commit()
    return ser.job(new)


# --------------------------------------------------------------------------- assets
@router.get("/assets/visual-checklist")
def visual_checklist(_: Principal = Depends(any_user)):
    return [{"key": k, "label": v} for k, v in VISUAL_CHECKLIST.items()]


@router.get("/assets/{asset_id}")
def get_asset(asset_id: uuid.UUID, db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    a = get_asset_or_404(db, asset_id)
    d = cat.current_dimension(db, a.variant_id)
    return ser.asset(a, d.id if d else None)


@router.post("/variants/{variant_id}/assets", status_code=201)
async def upload_variant_asset(variant_id: uuid.UUID, file: UploadFile = File(..., description="Binary glTF (.glb)"),
                               parent_asset_id: uuid.UUID | None = Form(default=None),
                               db: Session = Depends(get_db), p: Principal = Depends(require_roles(*ASSET_REVIEWERS))):
    v = cat.get_variant_or_404(db, variant_id)
    a = upload_asset(db, v, await file.read(), file.filename or "upload.glb", parent_asset_id, p)
    db.commit()
    return ser.asset(a)


@router.post("/assets/{asset_id}/reprocess")
def reprocess_asset(asset_id: uuid.UUID, body: ReprocessIn, db: Session = Depends(get_db),
                    p: Principal = Depends(require_roles(*ASSET_REVIEWERS))):
    a = get_asset_or_404(db, asset_id)
    reprocess(db, a, body.rotation_deg, body.auto_yaw, p)
    db.commit()
    return ser.asset(a)


@router.post("/assets/{asset_id}/preview")
async def upload_preview(asset_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                         p: Principal = Depends(require_roles(*GENERATORS))):
    a = get_asset_or_404(db, asset_id)
    save_preview(db, a, await file.read(), p)
    db.commit()
    return {"preview_url": ser.file_url(a.preview_file_id)}


@router.post("/assets/{asset_id}/review", status_code=201)
def review(asset_id: uuid.UUID, body: AssetReviewIn, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles(*ASSET_REVIEWERS))):
    a = get_asset_or_404(db, asset_id)
    review_asset(db, a, body.decision, body.checklist, body.comment, body.select_for_catalogue, p)
    db.commit()
    d = cat.current_dimension(db, a.variant_id)
    return ser.asset(a, d.id if d else None)


@router.post("/assets/{asset_id}/select")
def serve_asset(asset_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*ASSET_REVIEWERS))):
    a = get_asset_or_404(db, asset_id)
    select_asset(db, a)
    audit(db, p, "asset.selected", "asset", a.id)
    db.commit()
    return ser.asset(a)
