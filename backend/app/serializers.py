"""Model → JSON conversion. Money is returned as a string (exact two decimals); metres as numbers."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (AdmissionReview, AppUser, Asset3D, Category, GenerationEngine, GenerationJob, LinkCheck,
                     PriceObservation, Product, ProductImage, ProductVariant, Retailer, SetComponent,
                     VariantDimension)
from .security import file_url
from .services import catalogue as cat


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def money(d: Decimal | None) -> str | None:
    return None if d is None else f"{d:.2f}"


def num(d: Decimal | float | None) -> float | None:
    return None if d is None else float(d)


def user(u: AppUser | None) -> dict[str, Any] | None:
    if not u:
        return None
    return {"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": u.role,
            "is_active": u.is_active, "last_login_at": iso(u.last_login_at)}


def retailer(r: Retailer | None) -> dict[str, Any] | None:
    if not r:
        return None
    return {"id": str(r.id), "name": r.name, "slug": r.slug, "website_url": r.website_url, "city": r.city,
            "country": r.country, "contact_notes": r.contact_notes, "usage_terms": r.usage_terms,
            "is_active": r.is_active}


def category(c: Category | None) -> dict[str, Any] | None:
    if not c:
        return None
    return {"id": c.id, "code": c.code, "name": c.name, "product_group": c.product_group, "parent_id": c.parent_id,
            "default_placement": c.default_placement, "is_planar": c.is_planar, "is_supported": c.is_supported}


def dimension(d: VariantDimension | None) -> dict[str, Any] | None:
    if not d:
        return None
    return {"id": str(d.id), "revision": d.revision, "kind": d.kind, "width_m": num(d.width_m),
            "depth_m": num(d.depth_m), "height_m": num(d.height_m), "entered_unit": d.entered_unit,
            "entered_values": d.entered_values, "source_text": d.source_text,
            "source_axis_order": d.source_axis_order, "source_ref": d.source_ref, "observed_at": iso(d.observed_at),
            "is_current": d.is_current, "note": d.note, "created_at": iso(d.created_at)}


def price(p: PriceObservation | None) -> dict[str, Any] | None:
    if not p:
        return None
    return {"id": str(p.id), "outcome": p.outcome, "price_pkr": money(p.price_pkr),
            "compare_at_price_pkr": money(p.compare_at_price_pkr), "sale_unit": p.sale_unit,
            "availability": p.availability, "includes_delivery": p.includes_delivery, "source_url": p.source_url,
            "source_kind": p.source_kind, "checked_at": iso(p.checked_at), "failure_reason": p.failure_reason}


def link_check(lc: LinkCheck | None) -> dict[str, Any] | None:
    if not lc:
        return None
    return {"id": str(lc.id), "url": lc.url, "outcome": lc.outcome, "http_status": lc.http_status, "note": lc.note,
            "checked_at": iso(lc.checked_at)}


def image(i: ProductImage) -> dict[str, Any]:
    return {"id": str(i.id), "product_id": str(i.product_id), "variant_id": str(i.variant_id) if i.variant_id else None,
            "original_format": i.original_format, "width_px": i.width_px, "height_px": i.height_px, "role": i.role,
            "view_angle": i.view_angle, "depicts_variant": i.depicts_variant, "usable_for_3d": i.usable_for_3d,
            "reviewed": i.reviewed, "source_url": i.source_url, "sort_order": i.sort_order,
            "original_url": file_url(i.file_id), "processed_url": file_url(i.processed_file_id or i.file_id),
            "thumbnail_url": file_url(i.thumbnail_file_id or i.processed_file_id or i.file_id),
            "filename": i.file.original_filename if i.file else None, "created_at": iso(i.created_at)}


def set_component(c: SetComponent) -> dict[str, Any]:
    return {"id": str(c.id), "name": c.name, "category_id": c.category_id, "quantity": c.quantity,
            "width_m": num(c.width_m), "depth_m": num(c.depth_m), "height_m": num(c.height_m), "notes": c.notes,
            "sort_order": c.sort_order}


def engine(e: GenerationEngine, online: int = 0) -> dict[str, Any]:
    return {"code": e.code, "display_name": e.display_name, "kind": e.kind, "license": e.license,
            "is_open_source": e.is_open_source, "commercial_use_note": e.commercial_use_note,
            "supports_multi_image": e.supports_multi_image, "max_input_images": e.max_input_images,
            "required_views": e.required_views or [], "supports_texture": e.supports_texture,
            "min_vram_gb": e.min_vram_gb, "default_params": e.default_params, "homepage_url": e.homepage_url,
            "notes": e.notes, "is_enabled": e.is_enabled, "online_workers": online}


def job(j: GenerationJob, include_log: bool = False) -> dict[str, Any]:
    out = {"id": str(j.id), "variant_id": str(j.variant_id), "engine_code": j.engine_code,
           "engine_name": j.engine.display_name if j.engine else j.engine_code, "status": j.status,
           "params": j.params, "priority": j.priority, "worker_id": j.worker_id, "attempts": j.attempts,
           "max_attempts": j.max_attempts, "progress": j.progress, "error_message": j.error_message,
           "result_asset_id": str(j.result_asset_id) if j.result_asset_id else None,
           "input_image_ids": [str(i.image_id) for i in j.inputs], "runtime_meta": j.runtime_meta,
           "created_at": iso(j.created_at), "claimed_at": iso(j.claimed_at), "started_at": iso(j.started_at),
           "finished_at": iso(j.finished_at), "heartbeat_at": iso(j.heartbeat_at)}
    if include_log:
        out["log"] = j.log
    return out


def asset(a: Asset3D, current_dimension_id=None) -> dict[str, Any]:
    return {"id": str(a.id), "variant_id": str(a.variant_id), "version": a.version, "origin": a.origin,
            "engine_code": a.engine_code, "generation_job_id": str(a.generation_job_id) if a.generation_job_id else None,
            "parent_asset_id": str(a.parent_asset_id) if a.parent_asset_id else None,
            "dimension_id": str(a.dimension_id) if a.dimension_id else None,
            "checked_against_current_dimensions": bool(a.dimension_id and a.dimension_id == current_dimension_id),
            "status": a.status, "is_selected": a.is_selected, "orientation": a.orientation,
            "native_extents": a.native_extents, "scaled_extents_m": a.scaled_extents_m,
            "scale_factors": a.scale_factors, "triangle_count": a.triangle_count, "vertex_count": a.vertex_count,
            "texture_count": a.texture_count, "glb_size_bytes": a.glb_size_bytes,
            "processing_error": a.processing_error, "glb_url": file_url(a.glb_file_id),
            "source_url": file_url(a.source_file_id), "preview_url": file_url(a.preview_file_id),
            "qualified_at": iso(a.qualified_at), "created_at": iso(a.created_at),
            "checks": [{"code": c.code, "outcome": c.outcome, "message": c.message, "measured": c.measured,
                        "threshold": c.threshold, "by_person": c.checked_by is not None, "checked_at": iso(c.checked_at)}
                       for c in a.checks],
            "reviews": [{"id": str(r.id), "decision": r.decision, "checklist": r.checklist, "comment": r.comment,
                         "reviewer_id": str(r.reviewer_id), "created_at": iso(r.created_at)} for r in a.reviews]}


def admission_review(r: AdmissionReview) -> dict[str, Any]:
    return {"id": str(r.id), "decision": r.decision, "comment": r.comment, "reviewer_id": str(r.reviewer_id),
            "conditions": r.conditions, "created_at": iso(r.created_at)}


def variant_summary(db: Session, v: ProductVariant) -> dict[str, Any]:
    d = cat.current_dimension(db, v.id)
    p = cat.latest_price(db, v.id)
    selected = db.scalar(select(Asset3D).where(Asset3D.variant_id == v.id, Asset3D.is_selected.is_(True)))
    latest_asset = db.scalar(select(Asset3D).where(Asset3D.variant_id == v.id).order_by(Asset3D.version.desc()).limit(1))
    return {"id": str(v.id), "variant_key": v.variant_key, "variant_label": v.variant_label,
            "configuration": v.configuration, "status": v.status, "status_reason": v.status_reason,
            "sale_unit": v.sale_unit, "dimension": dimension(d), "latest_price": price(p),
            "asset_ready": bool(selected and d and selected.dimension_id == d.id),
            "latest_asset_status": latest_asset.status if latest_asset else None,
            "latest_asset_preview_url": file_url(latest_asset.preview_file_id) if latest_asset else None}


def product_summary(db: Session, p: Product) -> dict[str, Any]:
    primary = next((i for i in p.images if i.role == "primary"), p.images[0] if p.images else None)
    return {"id": str(p.id), "name": p.name, "brand": p.brand, "retailer": retailer(p.retailer),
            "category": category(p.category), "listing_url": p.listing_url, "source": p.source,
            "external_ref": p.external_ref, "image_count": len(p.images),
            "thumbnail_url": file_url(primary.thumbnail_file_id or primary.file_id) if primary else None,
            "variants": [variant_summary(db, v) for v in p.variants], "created_at": iso(p.created_at),
            "updated_at": iso(p.updated_at)}


def variant_detail(db: Session, v: ProductVariant) -> dict[str, Any]:
    from .services.assets import assets_for_variant  # local import to avoid a cycle

    p = v.product
    d = cat.current_dimension(db, v.id)
    prices = list(db.scalars(select(PriceObservation).where(PriceObservation.variant_id == v.id)
                             .order_by(PriceObservation.checked_at.desc()).limit(50)))
    links = list(db.scalars(select(LinkCheck).where(LinkCheck.variant_id == v.id)
                            .order_by(LinkCheck.checked_at.desc()).limit(20)))
    jobs = list(db.scalars(select(GenerationJob).where(GenerationJob.variant_id == v.id)
                           .order_by(GenerationJob.created_at.desc()).limit(50)))
    reviews = list(db.scalars(select(AdmissionReview).where(AdmissionReview.variant_id == v.id)
                              .order_by(AdmissionReview.created_at.desc()).limit(20)))
    conditions = [r.as_dict() for r in cat.evaluate_variant(db, v)]
    return {
        **variant_summary(db, v),
        "product": {"id": str(p.id), "name": p.name, "brand": p.brand, "description": p.description,
                    "listing_url": p.listing_url, "retailer_product_ref": p.retailer_product_ref,
                    "retailer": retailer(p.retailer), "category": category(p.category), "source": p.source,
                    "external_ref": p.external_ref,
                    "variants": [{"id": str(x.id), "variant_label": x.variant_label, "variant_key": x.variant_key,
                                  "status": x.status} for x in p.variants]},
        "listing_url": v.listing_url, "effective_listing_url": cat.effective_listing_url(v),
        "sale_unit_quantity": v.sale_unit_quantity, "sale_unit_note": v.sale_unit_note,
        "placement_type": v.placement_type, "notes": v.notes, "eligible_since": iso(v.eligible_since),
        "room_uses": [{"room_type": r.room_type, "use_tag": r.use_tag} for r in v.room_uses],
        "attributes": [{"key": a.key, "value": a.value, "colour_hex": a.colour_hex, "source": a.source,
                        "verified": a.verified, "confidence": a.confidence} for a in v.attributes],
        "dimensions": [dimension(x) for x in v.dimensions],
        "current_dimension_id": str(d.id) if d else None,
        "price_observations": [price(x) for x in prices],
        "link_checks": [link_check(x) for x in links],
        "set_components": [set_component(c) for c in v.set_components],
        "images": [image(i) for i in cat.variant_images(db, v)],
        "jobs": [job(j) for j in jobs],
        "assets": [asset(a, d.id if d else None) for a in assets_for_variant(db, v.id)],
        "admission": {"conditions": conditions,
                      "all_required_pass": all(c["passed"] for c in conditions if c["required"]),
                      "reviews": [admission_review(r) for r in reviews]},
        "created_at": iso(v.created_at), "updated_at": iso(v.updated_at),
    }
