"""Asset qualification pipeline (FR-3D-002, FR-3D-003, FR-3D-004, NFR-ACC-002, §6.2).

Runs in the CPU worker (app/worker.py) for every asset in status 'processing':

  1. load the uploaded GLB and bake every node transform into the geometry
  2. finite-coordinate and non-degenerate checks
  3. apply the reviewer's orientation (quarter turns) and optional auto-yaw
  4. centre the footprint, stand it on y = 0 and scale each axis to the recorded W/H/D
  5. export a self-contained metric GLB and re-open it
  6. per-axis extent tolerance, embedded resources, Khronos validator, triangle budget
  7. leave 'visual_review' as not_run: a person must approve the look

A passing asset goes to 'in_review'; any failed required check sends it to
'needs_correction'. Nothing here can mark an asset qualified.
"""
from __future__ import annotations

import io
import json
import logging
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import get_settings
from ..domain import mesh_math as mm
from ..enums import AssetStatus, CheckOutcome, JobStatus
from ..models import Asset3D, AssetCheck, GenerationJob, ProductVariant, StoredFile, VariantDimension
from ..storage import read_bytes, save_bytes
from .catalogue import current_dimension

log = logging.getLogger("naqshkaar.assets")
settings = get_settings()

# Checks whose failure blocks qualification. 'warn' never blocks.
REQUIRED_CHECKS = ("file_readable", "geometry_finite", "geometry_non_degenerate", "dimensions_available",
                   "extent_width", "extent_depth", "extent_height", "scale_distortion", "glb_reload",
                   "embedded_resources", "gltf_validator", "visual_review")


@dataclass
class CheckSet:
    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, code: str, outcome: str, message: str = "", measured: Any = None, threshold: Any = None) -> None:
        self.items[code] = {"outcome": outcome, "message": message, "measured": measured, "threshold": threshold}

    def failed(self) -> list[str]:
        return [c for c, v in self.items.items() if v["outcome"] == CheckOutcome.fail.value]


def _bake(scene) -> tuple[Any, np.ndarray, int]:
    """Return (scene with identity node transforms, all vertices, triangle count)."""
    import trimesh

    baked = trimesh.Scene()
    all_verts, tris = [], 0
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        geom = scene.geometry[geom_name].copy()
        if not hasattr(geom, "vertices"):
            continue
        geom.apply_transform(transform)
        baked.add_geometry(geom, node_name=node, geom_name=f"{geom_name}_{node}")
        all_verts.append(np.asarray(geom.vertices, dtype=float))
        tris += len(getattr(geom, "faces", []))
    verts = np.vstack(all_verts) if all_verts else np.zeros((0, 3))
    return baked, verts, tris


def _apply(scene, matrix: np.ndarray) -> None:
    for geom in scene.geometry.values():
        geom.apply_transform(matrix)


def _vertices(scene) -> np.ndarray:
    parts = [np.asarray(g.vertices, dtype=float) for g in scene.geometry.values() if hasattr(g, "vertices")]
    return np.vstack(parts) if parts else np.zeros((0, 3))


def _run_validator(glb: bytes) -> tuple[str, str, Any]:
    """Khronos glTF-Validator via Node (see backend/tools). Returns (outcome, message, measured)."""
    if not settings.gltf_validator_cmd:
        return CheckOutcome.not_run.value, "validator disabled (GLTF_VALIDATOR_CMD empty)", None
    with tempfile.NamedTemporaryFile(suffix=".glb") as tmp:
        tmp.write(glb)
        tmp.flush()
        try:
            proc = subprocess.run(shlex.split(settings.gltf_validator_cmd) + [tmp.name], capture_output=True,
                                  text=True, timeout=120)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckOutcome.not_run.value, f"validator unavailable: {exc}", None
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return CheckOutcome.not_run.value, f"validator output unreadable: {proc.stderr[-300:]}", None
    issues = report.get("issues", {})
    measured = {k: issues.get(k) for k in ("numErrors", "numWarnings", "numInfos")}
    if issues.get("numErrors", 0) > 0:
        msgs = [m.get("message") for m in issues.get("messages", []) if m.get("severity") == 0][:5]
        return CheckOutcome.fail.value, "; ".join(filter(None, msgs)) or "validator reported errors", measured
    return CheckOutcome.pass_.value, f"{issues.get('numWarnings', 0)} warning(s)", measured


def process_asset(db: Session, asset: Asset3D) -> None:
    import trimesh

    checks = CheckSet()
    variant = db.get(ProductVariant, asset.variant_id)
    dim: VariantDimension | None = current_dimension(db, variant.id)
    asset.dimension_id = dim.id if dim else None
    asset.processing_error = None

    def finish(status: str, error: str | None = None) -> None:
        _store_checks(db, asset, checks)
        asset.status = status
        asset.processing_error = error
        asset.processing_started_at = None
        _finish_job(db, asset, status, error)

    # 1 load -------------------------------------------------------------------
    src = db.get(StoredFile, asset.source_file_id)
    try:
        scene = trimesh.load(io.BytesIO(read_bytes(src)), file_type="glb", force="scene")
        baked, verts, tris = _bake(scene)
        if verts.size == 0:
            raise ValueError("no mesh geometry found")
        checks.add("file_readable", "pass", f"{len(baked.geometry)} mesh part(s)")
    except Exception as exc:  # noqa: BLE001
        checks.add("file_readable", "fail", f"could not read GLB: {exc}")
        return finish(AssetStatus.needs_correction.value, str(exc))

    # 2 geometry ---------------------------------------------------------------
    if not mm.is_finite(verts):
        checks.add("geometry_finite", "fail", "NaN or infinite coordinates")
        return finish(AssetStatus.needs_correction.value, "non-finite geometry")
    checks.add("geometry_finite", "pass")

    # 3 orientation --------------------------------------------------------------
    orient = dict(asset.orientation or {})
    rx, ry, rz = (list(orient.get("rotation_deg") or [0, 0, 0]) + [0, 0, 0])[:3]
    _apply(baked, mm.rotation_matrix_deg(rx, ry, rz))
    verts = _vertices(baked)
    lo, hi = mm.bounds(verts)
    ext = hi - lo
    asset.native_extents = {"x": float(ext[0]), "y": float(ext[1]), "z": float(ext[2])}
    if (ext <= 1e-6).any():
        checks.add("geometry_non_degenerate", "fail", "zero extent on an axis", asset.native_extents)
        return finish(AssetStatus.needs_correction.value, "degenerate geometry")
    checks.add("geometry_non_degenerate", "pass", measured=asset.native_extents)

    have_dims = bool(dim and dim.kind == "assembled" and dim.width_m and dim.depth_m and dim.height_m)
    if have_dims:
        W, D, H = float(dim.width_m), float(dim.depth_m), float(dim.height_m)
        checks.add("dimensions_available", "pass", f"revision {dim.revision}: {W} × {D} × {H} m")
        yaw_applied = 0
        if orient.get("auto_yaw", True):
            yaw_applied = mm.choose_yaw_quarter_turns(float(ext[0]), float(ext[2]), W, D)
            if yaw_applied:
                _apply(baked, mm.rotation_matrix_deg(0, 90, 0))
                verts = _vertices(baked)
        orient["auto_yaw_applied_deg"] = 90 * yaw_applied
        asset.orientation = orient

        # 4 scale --------------------------------------------------------------
        plan = mm.plan_metric_scale(verts, width=W, depth=D, height=H)
        _apply(baked, plan.matrix)
        asset.scale_factors = {**plan.factors, "distortion": plan.distortion}
        if plan.distortion > settings.asset_distortion_fail:
            checks.add("scale_distortion", "fail",
                       f"per-axis scale differs by ×{plan.distortion:.2f}; the mesh proportions do not match the "
                       "product. Try another orientation, image or engine.", asset.scale_factors,
                       {"warn": settings.asset_distortion_warn, "fail": settings.asset_distortion_fail})
        elif plan.distortion > settings.asset_distortion_warn:
            checks.add("scale_distortion", "warn", f"proportions stretched ×{plan.distortion:.2f}; check visually",
                       asset.scale_factors, {"warn": settings.asset_distortion_warn})
        else:
            checks.add("scale_distortion", "pass", f"×{plan.distortion:.2f}", asset.scale_factors)
    else:
        checks.add("dimensions_available", "fail",
                   "No current assembled W × D × H. Add source-backed dimensions, then reprocess.")
        # Still normalise placement so the preview is usable.
        lo, hi = mm.bounds(verts)
        centre = (lo + hi) / 2
        t = np.eye(4)
        t[:3, 3] = [-centre[0], -lo[1], -centre[2]]
        _apply(baked, t)

    # 5 export and reload ----------------------------------------------------
    try:
        glb = baked.export(file_type="glb")
        gltf, _ = mm.parse_glb(glb)
        reloaded = trimesh.load(io.BytesIO(glb), file_type="glb", force="scene")
        _, rverts, rtris = _bake(reloaded)
        checks.add("glb_reload", "pass", "exported GLB re-opens")
    except Exception as exc:  # noqa: BLE001
        checks.add("glb_reload", "fail", f"export failed: {exc}")
        return finish(AssetStatus.needs_correction.value, str(exc))

    out_ext = mm.extents_by_axis(rverts)
    asset.scaled_extents_m = out_ext
    if have_dims:
        for axis, target in (("width", W), ("depth", D), ("height", H)):
            tol = mm.extent_tolerance_m(target, settings.asset_extent_min_tolerance_m, settings.asset_extent_rel_tolerance)
            ok = mm.within_tolerance(out_ext[axis], target, settings.asset_extent_min_tolerance_m,
                                     settings.asset_extent_rel_tolerance)
            checks.add(f"extent_{axis}", "pass" if ok else "fail",
                       f"{out_ext[axis]:.4f} m vs {target:.4f} m (±{tol * 1000:.1f} mm)",
                       {"measured_m": out_ext[axis]}, {"expected_m": target, "tolerance_m": tol})

    # 6 file checks ------------------------------------------------------------
    external = mm.external_resources(gltf)
    checks.add("embedded_resources", "fail" if external else "pass",
               "; ".join(external) if external else f"{len(gltf.get('images', []))} embedded texture(s)")
    v_out, v_msg, v_meas = _run_validator(glb)
    if v_out == CheckOutcome.not_run.value and settings.require_gltf_validator:
        v_out, v_msg = CheckOutcome.fail.value, v_msg + " (REQUIRE_GLTF_VALIDATOR is on)"
    checks.add("gltf_validator", v_out, v_msg, v_meas)
    checks.add("triangle_budget", "pass" if rtris <= settings.asset_triangle_budget else "warn",
               f"{rtris:,} triangles", {"triangles": rtris}, {"budget": settings.asset_triangle_budget})
    checks.add("visual_review", "not_run", "Awaiting a reviewer: correct item, silhouette, parts, no staging props")

    stored = save_bytes(db, glb, "model/gltf-binary", prefix="assets/glb",
                        filename=f"{variant.id}-v{asset.version}.glb")
    asset.glb_file_id = stored.id
    asset.glb_size_bytes = len(glb)
    asset.triangle_count = rtris
    asset.vertex_count = int(len(rverts))
    asset.texture_count = len(gltf.get("images", []))
    finish(AssetStatus.needs_correction.value if checks.failed() else AssetStatus.in_review.value,
           "; ".join(checks.failed()) or None)


def _store_checks(db: Session, asset: Asset3D, checks: CheckSet) -> None:
    # Reprocessing changes what the reviewer would see, so an earlier visual review no longer
    # applies. Its decision stays in asset_review; the check rows are rebuilt from scratch.
    db.execute(delete(AssetCheck).where(AssetCheck.asset_id == asset.id))
    db.flush()
    for code, c in checks.items.items():
        db.add(AssetCheck(asset_id=asset.id, code=code, outcome=c["outcome"], message=c["message"] or None,
                          measured=_jsonable(c["measured"]), threshold=_jsonable(c["threshold"])))


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (dict, list)):
        return v
    return {"value": v}


def _finish_job(db: Session, asset: Asset3D, status: str, error: str | None) -> None:
    if not asset.generation_job_id:
        return
    job = db.get(GenerationJob, asset.generation_job_id)
    if not job or job.status not in (JobStatus.uploaded.value, JobStatus.postprocessing.value):
        return
    job.status = JobStatus.succeeded.value
    job.finished_at = datetime.now(timezone.utc)
    note = "passed automated checks; awaiting visual review" if status == AssetStatus.in_review.value \
        else f"generated, but checks need attention: {error}"
    job.log = (job.log + f"[studio] asset v{asset.version} {note}\n")[-60_000:]
