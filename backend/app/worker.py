"""CPU worker: runs asset qualification and housekeeping.

    python -m app.worker            # loop forever
    python -m app.worker --once     # one pass, for cron or debugging

Each pass:
  1. re-queue generation jobs whose worker stopped sending heartbeats
  2. claim one asset in status 'processing' (SKIP LOCKED) and qualify it
Run as many copies as you like; claims never collide.
"""
from __future__ import annotations

import argparse
import logging
import time
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from .config import get_settings
from .db import SessionLocal
from .enums import AssetStatus, JobStatus
from .models import Asset3D, GenerationJob
from .services.asset_pipeline import process_asset
from .services.jobs import requeue_stale_jobs

log = logging.getLogger("naqshkaar.worker")
settings = get_settings()


def claim_asset(db) -> Asset3D | None:
    stale = datetime.now(timezone.utc) - timedelta(minutes=settings.asset_processing_stale_minutes)
    asset = db.scalar(select(Asset3D)
                      .where(Asset3D.status == AssetStatus.processing.value,
                             or_(Asset3D.processing_started_at.is_(None), Asset3D.processing_started_at < stale))
                      .order_by(Asset3D.created_at)
                      .with_for_update(skip_locked=True).limit(1))
    if asset is None:
        return None
    asset.processing_started_at = datetime.now(timezone.utc)
    if asset.generation_job_id:
        job = db.get(GenerationJob, asset.generation_job_id)
        if job and job.status == JobStatus.uploaded.value:
            job.status = JobStatus.postprocessing.value
    db.commit()
    return asset


def run_once() -> bool:
    """Returns True if an asset was processed (so the loop can continue without sleeping)."""
    with SessionLocal() as db:
        n = requeue_stale_jobs(db)
        if n:
            log.warning("re-queued %d stale generation job(s)", n)
        db.commit()

    with SessionLocal() as db:
        asset = claim_asset(db)
        if asset is None:
            return False
        log.info("qualifying asset %s (variant %s, v%d)", asset.id, asset.variant_id, asset.version)
        try:
            process_asset(db, asset)
            db.commit()
            log.info("asset %s -> %s", asset.id, asset.status)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.error("asset %s failed: %s", asset.id, exc)
            asset = db.get(Asset3D, asset.id)
            asset.status = AssetStatus.needs_correction.value
            asset.processing_error = f"pipeline error: {exc}\n{traceback.format_exc()[-1500:]}"
            asset.processing_started_at = None
            if asset.generation_job_id:
                job = db.get(GenerationJob, asset.generation_job_id)
                if job and job.status in (JobStatus.uploaded.value, JobStatus.postprocessing.value):
                    job.status = JobStatus.failed.value
                    job.error_message = f"qualification pipeline error: {exc}"
                    job.finished_at = datetime.now(timezone.utc)
            db.commit()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.once:
        run_once()
        return
    log.info("CPU worker started (poll %.1fs)", settings.cpu_worker_poll_seconds)
    while True:
        try:
            busy = run_once()
        except Exception:  # noqa: BLE001 - keep the loop alive through DB restarts
            log.exception("worker pass failed")
            busy = False
        if not busy:
            time.sleep(settings.cpu_worker_poll_seconds)


if __name__ == "__main__":
    main()
