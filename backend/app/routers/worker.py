"""HTTP protocol for 3D generation workers (scope: worker). See generator/README.md."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Principal, require_api_key
from ..domain import mesh_math as mm
from ..schemas import WorkerFailure, WorkerHello, WorkerProgress
from ..services import jobs as jobsvc
from ..storage import save_bytes

router = APIRouter(prefix="/api/worker", tags=["worker"])
settings = get_settings()
worker_key = require_api_key("worker")


@router.post("/hello")
def hello(body: WorkerHello, db: Session = Depends(get_db), p: Principal = Depends(worker_key)):
    w = jobsvc.register_worker(db, body.model_dump(), p)
    db.commit()
    return {"worker_id": w.id, "poll_seconds": 5, "job_stale_minutes": settings.job_stale_minutes}


@router.post("/claim")
def claim(body: WorkerHello, db: Session = Depends(get_db), p: Principal = Depends(worker_key)):
    jobsvc.register_worker(db, body.model_dump(), p)
    job = jobsvc.claim_next_job(db, body.worker_id, body.engines)
    if not job:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    payload = jobsvc.job_payload(db, job)
    db.commit()
    return payload


@router.post("/jobs/{job_id}/progress")
def progress(job_id: uuid.UUID, body: WorkerProgress, db: Session = Depends(get_db), _: Principal = Depends(worker_key)):
    job = jobsvc.get_worker_job(db, job_id, body.worker_id)
    state = jobsvc.record_progress(db, job, body.progress, body.log)
    db.commit()
    return {"status": state, "cancel": state == "cancelled"}


@router.post("/jobs/{job_id}/result")
async def result(job_id: uuid.UUID, worker_id: str = Form(...), meta: str = Form(default="{}"),
                 file: UploadFile = File(..., description="GLB, Y-up, any scale"),
                 db: Session = Depends(get_db), _: Principal = Depends(worker_key)):
    job = jobsvc.get_worker_job(db, job_id, worker_id)
    data = await file.read()
    if len(data) > settings.max_mesh_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Mesh too large")
    try:
        mm.parse_glb(data)
    except ValueError as exc:
        jobsvc.fail_job(db, job, f"worker uploaded an invalid GLB: {exc}", None, retryable=True)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    try:
        meta_obj = json.loads(meta) if meta else {}
    except json.JSONDecodeError:
        meta_obj = {"raw": meta[:2000]}
    raw = save_bytes(db, data, "model/gltf-binary", prefix="assets/source",
                     filename=f"{job.engine_code}-{job.id}.glb")
    asset = jobsvc.accept_result(db, job, raw.id, meta_obj)
    db.commit()
    return {"asset_id": str(asset.id), "status": job.status}


@router.post("/jobs/{job_id}/fail")
def fail(job_id: uuid.UUID, body: WorkerFailure, db: Session = Depends(get_db), _: Principal = Depends(worker_key)):
    job = jobsvc.get_worker_job(db, job_id, body.worker_id)
    jobsvc.fail_job(db, job, body.error, body.log, body.retryable)
    db.commit()
    return {"status": job.status}
