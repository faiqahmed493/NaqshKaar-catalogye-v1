"""3D generation job queue (database-backed, pull model).

GPU workers never connect to the database. They poll the HTTP worker API with an
API key, download inputs through signed URLs and upload a GLB. That lets a worker
run on a lab GPU, a team laptop or Google Colab behind a tunnel.

Job states:
  queued → claimed → running → uploaded → postprocessing → succeeded
                      └─(error)→ queued again until max_attempts, then failed
  any active state → cancelled (by a user)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import Principal
from ..enums import ACTIVE_JOB_STATUSES, AssetOrigin, AssetStatus, JobStatus
from ..models import (Asset3D, GenerationEngine, GenerationJob, GenerationWorker, JobInputImage, ProductImage,
                      ProductVariant)
from ..security import file_url
from .audit import audit
from .catalogue import current_dimension

settings = get_settings()
MAX_LOG_CHARS = 60_000


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _append_log(job: GenerationJob, line: str | None) -> None:
    if not line:
        return
    job.log = (job.log + line.rstrip() + "\n")[-MAX_LOG_CHARS:]


# --------------------------------------------------------------------------- creating jobs
def create_jobs(db: Session, v: ProductVariant, engine_codes: list[str], image_ids: list[uuid.UUID],
                params_by_engine: dict[str, dict[str, Any]] | None, priority: int, actor: Principal) -> list[GenerationJob]:
    if not engine_codes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one engine")
    if not image_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one image")
    images = list(db.scalars(select(ProductImage).where(ProductImage.id.in_(image_ids))))
    by_id = {i.id: i for i in images}
    ordered: list[ProductImage] = []
    for iid in image_ids:
        img = by_id.get(iid)
        if img is None or img.product_id != v.product_id or img.variant_id not in (None, v.id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Image {iid} does not belong to this variant")
        if not img.usable_for_3d:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Image {iid} is marked not usable for 3D")
        ordered.append(img)

    dim = current_dimension(db, v.id)
    jobs: list[GenerationJob] = []
    for code in dict.fromkeys(engine_codes):  # de-duplicate, keep order
        eng = db.get(GenerationEngine, code)
        if not eng or not eng.is_enabled:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Engine '{code}' is not available")
        chosen = ordered if eng.supports_multi_image else ordered[:1]
        chosen = chosen[: eng.max_input_images]
        if eng.required_views:
            views = {i.view_angle for i in chosen}
            missing = [rv for rv in eng.required_views if rv not in views]
            if missing:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    f"{eng.display_name} needs images tagged as: {', '.join(missing)}")
        params = {**(eng.default_params or {}), **((params_by_engine or {}).get(code) or {})}
        job = GenerationJob(variant_id=v.id, engine_code=code, params=params, priority=priority,
                            dimension_id=dim.id if dim else None, requested_by=actor.user_id)
        job.inputs = [JobInputImage(image_id=i.id, position=n) for n, i in enumerate(chosen)]
        db.add(job)
        jobs.append(job)
    db.flush()
    for j in jobs:
        audit(db, actor, "job.created", "variant", v.id, {"job_id": str(j.id), "engine": j.engine_code})
    return jobs


def cancel_job(db: Session, job: GenerationJob, actor: Principal) -> None:
    if job.status not in [s.value for s in ACTIVE_JOB_STATUSES]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job is already {job.status}")
    if job.status in (JobStatus.uploaded.value, JobStatus.postprocessing.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "The result is already being processed")
    job.status = JobStatus.cancelled.value
    job.finished_at = now_utc()
    _append_log(job, f"[studio] cancelled by {actor.label}")
    audit(db, actor, "job.cancelled", "job", job.id)


def retry_job(db: Session, job: GenerationJob, actor: Principal) -> GenerationJob:
    if job.status not in (JobStatus.failed.value, JobStatus.cancelled.value, JobStatus.succeeded.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only finished jobs can be re-run")
    v = db.get(ProductVariant, job.variant_id)
    dim = current_dimension(db, v.id)
    new = GenerationJob(variant_id=job.variant_id, engine_code=job.engine_code, params=dict(job.params),
                        priority=job.priority, dimension_id=dim.id if dim else None, requested_by=actor.user_id)
    new.inputs = [JobInputImage(image_id=i.image_id, position=i.position) for i in job.inputs]
    db.add(new)
    db.flush()
    audit(db, actor, "job.retried", "job", job.id, {"new_job_id": str(new.id)})
    return new


# --------------------------------------------------------------------------- worker protocol
def register_worker(db: Session, data: dict[str, Any], actor: Principal) -> GenerationWorker:
    wid = data["worker_id"]
    w = db.get(GenerationWorker, wid)
    if not w:
        w = GenerationWorker(id=wid)
        db.add(w)
    w.engines = list(data.get("engines") or [])
    w.hostname = data.get("hostname")
    w.gpu_name = data.get("gpu_name")
    w.gpu_vram_gb = data.get("gpu_vram_gb")
    w.version = data.get("version")
    w.api_key_id = actor.api_key_id
    w.last_seen_at = now_utc()
    return w


def claim_next_job(db: Session, worker_id: str, engines: list[str]) -> GenerationJob | None:
    """Atomically claim the highest-priority queued job this worker can run (SKIP LOCKED)."""
    if not engines:
        return None
    row = db.execute(text("""
        SELECT j.id FROM generation_job j
        JOIN generation_engine e ON e.code = j.engine_code AND e.is_enabled
        WHERE j.status = 'queued' AND j.engine_code = ANY(CAST(:engines AS text[]))
        ORDER BY j.priority DESC, j.created_at
        FOR UPDATE OF j SKIP LOCKED
        LIMIT 1
    """), {"engines": engines}).first()
    if not row:
        return None
    job = db.get(GenerationJob, row[0])
    job.status = JobStatus.claimed.value
    job.worker_id = worker_id
    job.attempts += 1
    job.claimed_at = job.heartbeat_at = now_utc()
    job.progress = 0
    _append_log(job, f"[studio] claimed by {worker_id} (attempt {job.attempts}/{job.max_attempts})")
    return job


def job_payload(db: Session, job: GenerationJob) -> dict[str, Any]:
    v = db.get(ProductVariant, job.variant_id)
    dim = current_dimension(db, v.id)
    inputs = []
    for ji in job.inputs:
        img = ji.image
        fid = img.processed_file_id or img.file_id
        inputs.append({"image_id": str(img.id), "position": ji.position, "url": file_url(fid),
                       "view_angle": img.view_angle, "role": img.role, "filename": f"{img.id}.png"})
    return {
        "job_id": str(job.id), "engine": job.engine_code, "params": job.params, "attempt": job.attempts,
        "inputs": inputs,
        "product": {"variant_id": str(v.id), "name": v.product.name, "variant_label": v.variant_label,
                    "category": v.product.category.code if v.product.category else None},
        "target_dimensions_m": ({"width": float(dim.width_m) if dim.width_m else None,
                                 "depth": float(dim.depth_m) if dim.depth_m else None,
                                 "height": float(dim.height_m) if dim.height_m else None} if dim else None),
    }


def get_worker_job(db: Session, job_id: uuid.UUID, worker_id: str) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if not job or job.worker_id != worker_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found for this worker")
    return job


def record_progress(db: Session, job: GenerationJob, progress: float | None, log: str | None) -> str:
    """Returns the job status so the worker can stop work on a cancelled job."""
    if job.status == JobStatus.cancelled.value:
        return job.status
    if job.status == JobStatus.claimed.value:
        job.status = JobStatus.running.value
        job.started_at = now_utc()
    job.heartbeat_at = now_utc()
    if progress is not None:
        job.progress = max(0.0, min(100.0, float(progress)))
    _append_log(job, log)
    return job.status


def next_asset_version(db: Session, variant_id: uuid.UUID) -> int:
    return (db.scalar(select(func.max(Asset3D.version)).where(Asset3D.variant_id == variant_id)) or 0) + 1


def accept_result(db: Session, job: GenerationJob, raw_file_id: uuid.UUID, meta: dict[str, Any]) -> Asset3D:
    if job.status == JobStatus.cancelled.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job was cancelled")
    if job.status not in (JobStatus.claimed.value, JobStatus.running.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job is {job.status}; result not expected")
    job.raw_output_file_id = raw_file_id
    job.status = JobStatus.uploaded.value
    job.progress = 100
    job.heartbeat_at = now_utc()
    job.runtime_meta = meta or {}
    _append_log(job, "[studio] result uploaded; queued for qualification checks")
    asset = Asset3D(variant_id=job.variant_id, version=next_asset_version(db, job.variant_id),
                    origin=AssetOrigin.generated.value, engine_code=job.engine_code, generation_job_id=job.id,
                    source_file_id=raw_file_id, status=AssetStatus.processing.value,
                    orientation={"rotation_deg": [0, 0, 0], "auto_yaw": True}, created_by=job.requested_by)
    db.add(asset)
    db.flush()
    job.result_asset_id = asset.id
    return asset


def fail_job(db: Session, job: GenerationJob, error: str, log: str | None, retryable: bool = True) -> None:
    _append_log(job, log)
    _append_log(job, f"[worker] error: {error}")
    job.error_message = error[:4000]
    if retryable and job.attempts < job.max_attempts and job.status != JobStatus.cancelled.value:
        job.status = JobStatus.queued.value
        job.worker_id = None
        _append_log(job, "[studio] re-queued for another attempt")
    else:
        job.status = JobStatus.failed.value
        job.finished_at = now_utc()


def requeue_stale_jobs(db: Session) -> int:
    """Workers that stop sending heartbeats lose their job (crash, Colab disconnect)."""
    cutoff = now_utc() - timedelta(minutes=settings.job_stale_minutes)
    stale = list(db.scalars(select(GenerationJob).where(
        GenerationJob.status.in_([JobStatus.claimed.value, JobStatus.running.value]),
        # of=: lock only the job rows; PostgreSQL rejects FOR UPDATE on the joined-loaded engine (outer join).
        GenerationJob.heartbeat_at < cutoff).with_for_update(skip_locked=True, of=GenerationJob)))
    for job in stale:
        fail_job(db, job, f"no heartbeat from {job.worker_id} for {settings.job_stale_minutes} min", None)
    return len(stale)


def online_workers(db: Session) -> list[GenerationWorker]:
    cutoff = now_utc() - timedelta(seconds=settings.worker_online_seconds)
    return list(db.scalars(select(GenerationWorker).where(GenerationWorker.last_seen_at >= cutoff)))
