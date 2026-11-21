"""3D asset actions: manual or corrected uploads, reprocessing, human review and selection."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import Principal
from ..domain import mesh_math as mm
from ..enums import AssetDecision, AssetOrigin, AssetStatus, CheckOutcome
from ..models import Asset3D, AssetCheck, AssetReview, ProductVariant
from ..storage import save_bytes
from .audit import audit
from .catalogue import current_dimension
from .jobs import next_asset_version

settings = get_settings()

# The six points of the §6.2 visual review. All must be true to approve.
VISUAL_CHECKLIST = {
    "correct_item": "Shows the right product and configuration",
    "silhouette": "Major silhouette matches the product images",
    "components": "Visible components are present (legs, arms, shelves, shade)",
    "no_staging_objects": "No unrelated staging objects (rugs, plants, props) fused in",
    "no_missing_parts": "No gross missing or broken parts",
    "no_scale_distortion": "No severe stretching or squashing",
}


def get_asset_or_404(db: Session, asset_id: uuid.UUID) -> Asset3D:
    a = db.get(Asset3D, asset_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return a


def upload_asset(db: Session, v: ProductVariant, data: bytes, filename: str, parent_id: uuid.UUID | None,
                 actor: Principal) -> Asset3D:
    """A GLB made or fixed by a person (e.g. cleaned up in Blender). It repeats every check (§6.2)."""
    if len(data) > settings.max_mesh_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Mesh larger than {settings.max_mesh_upload_mb} MB")
    try:
        mm.parse_glb(data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{filename}: {exc}. Export a binary glTF (.glb) with embedded textures.") from exc
    parent = None
    if parent_id:
        parent = get_asset_or_404(db, parent_id)
        if parent.variant_id != v.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Parent asset belongs to another variant")
    raw = save_bytes(db, data, "model/gltf-binary", prefix="assets/source", filename=filename, user_id=actor.user_id)
    asset = Asset3D(variant_id=v.id, version=next_asset_version(db, v.id),
                    origin=AssetOrigin.corrected.value if parent else AssetOrigin.manual_upload.value,
                    engine_code=parent.engine_code if parent else None, parent_asset_id=parent.id if parent else None,
                    source_file_id=raw.id, status=AssetStatus.processing.value, created_by=actor.user_id,
                    orientation={"rotation_deg": [0, 0, 0], "auto_yaw": False} if parent else
                    {"rotation_deg": [0, 0, 0], "auto_yaw": True})
    db.add(asset)
    db.flush()
    if parent and parent.status in (AssetStatus.in_review.value, AssetStatus.needs_correction.value):
        parent.status = AssetStatus.rejected.value
    audit(db, actor, "asset.uploaded", "variant", v.id, {"asset_id": str(asset.id), "parent": str(parent_id) if parent_id else None})
    return asset


def reprocess(db: Session, asset: Asset3D, rotation_deg: list[float] | None, auto_yaw: bool | None,
              actor: Principal) -> None:
    """Re-run qualification, e.g. after adding dimensions or turning the model upright."""
    if asset.status == AssetStatus.processing.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already processing")
    if asset.status == AssetStatus.qualified.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Qualified assets are immutable; upload a corrected version")
    orient = dict(asset.orientation or {})
    if rotation_deg is not None:
        if len(rotation_deg) != 3 or any(float(r) % 90 for r in rotation_deg):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rotations are quarter turns: multiples of 90°")
        orient["rotation_deg"] = [float(r) % 360 for r in rotation_deg]
    if auto_yaw is not None:
        orient["auto_yaw"] = auto_yaw
    asset.orientation = orient
    asset.status = AssetStatus.processing.value
    asset.processing_started_at = None
    asset.is_selected = False
    audit(db, actor, "asset.reprocess", "asset", asset.id, {"orientation": orient})


def save_preview(db: Session, asset: Asset3D, png: bytes, actor: Principal) -> None:
    if not png.startswith(b"\x89PNG"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Preview must be a PNG")
    f = save_bytes(db, png, "image/png", prefix="assets/preview", filename=f"{asset.id}.png", user_id=actor.user_id)
    asset.preview_file_id = f.id


def review_asset(db: Session, asset: Asset3D, decision: str, checklist: dict[str, bool], comment: str | None,
                 select_for_catalogue: bool, actor: Principal) -> AssetReview:
    if actor.user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Asset review needs a human reviewer")
    if asset.status not in (AssetStatus.in_review.value, AssetStatus.needs_correction.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Asset is {asset.status}; only assets awaiting review can be reviewed")

    if decision == AssetDecision.approve.value:
        problems: list[str] = []
        unticked = [label for key, label in VISUAL_CHECKLIST.items() if not checklist.get(key)]
        if unticked:
            problems.append("Visual checklist incomplete: " + "; ".join(unticked))
        failed = [c.code for c in asset.checks if c.outcome == CheckOutcome.fail.value and c.code != "visual_review"]
        if failed:
            problems.append("Automated checks failed: " + ", ".join(failed))
        dim = current_dimension(db, asset.variant_id)
        if not dim or asset.dimension_id != dim.id:
            problems.append("Asset was not checked against the current dimension revision; reprocess it first")
        if not asset.glb_file_id:
            problems.append("No processed GLB")
        if problems:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "Cannot approve", "problems": problems})

    review = AssetReview(asset_id=asset.id, reviewer_id=actor.user.id, decision=decision,
                         checklist={k: bool(checklist.get(k)) for k in VISUAL_CHECKLIST}, comment=comment)
    db.add(review)

    visual = next((c for c in asset.checks if c.code == "visual_review"), None)
    if visual is None:
        visual = AssetCheck(asset_id=asset.id, code="visual_review", outcome=CheckOutcome.not_run.value)
        db.add(visual)
    visual.outcome = CheckOutcome.pass_.value if decision == "approve" else CheckOutcome.fail.value
    visual.message = comment or ("Approved" if decision == "approve" else "Not approved")
    visual.checked_by = actor.user.id
    visual.checked_at = datetime.now(timezone.utc)
    visual.measured = review.checklist

    now = datetime.now(timezone.utc)
    if decision == AssetDecision.approve.value:
        asset.status = AssetStatus.qualified.value
        asset.qualified_at = now
        asset.qualified_by = actor.user.id
        if select_for_catalogue:
            select_asset(db, asset)
    elif decision == AssetDecision.needs_correction.value:
        asset.status = AssetStatus.needs_correction.value
    else:
        asset.status = AssetStatus.rejected.value
    audit(db, actor, f"asset.{decision}", "asset", asset.id, {"comment": comment})
    return review


def select_asset(db: Session, asset: Asset3D) -> None:
    """Make this the asset the catalogue serves for its variant (one per variant)."""
    if asset.status != AssetStatus.qualified.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only qualified assets can be selected")
    db.execute(update(Asset3D).where(Asset3D.variant_id == asset.variant_id, Asset3D.id != asset.id)
               .values(is_selected=False).execution_options(synchronize_session="fetch"))
    db.flush()
    asset.is_selected = True


def asset_summary_checks(asset: Asset3D) -> dict[str, Any]:
    counts: dict[str, int] = {"pass": 0, "fail": 0, "warn": 0, "not_run": 0}
    for c in asset.checks:
        counts[c.outcome] = counts.get(c.outcome, 0) + 1
    return counts


def assets_for_variant(db: Session, variant_id: uuid.UUID) -> list[Asset3D]:
    return list(db.scalars(select(Asset3D).where(Asset3D.variant_id == variant_id).order_by(Asset3D.version.desc())))
