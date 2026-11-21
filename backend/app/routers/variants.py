from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import ASSET_REVIEWERS, EDITORS, Principal, any_user, require_roles
from ..enums import UserRole, VariantStatus
from ..models import SetComponent, VariantAttribute, VariantRoomUse
from ..schemas import (AdmissionReviewIn, AttributeIn, DimensionIn, LinkCheckIn, PriceIn, PublishIn, RetireIn,
                       RoomUseIn, SetComponentIn, VariantPatch)
from ..services import catalogue as cat
from ..services.assets import get_asset_or_404, review_asset
from ..services.audit import audit

router = APIRouter(prefix="/api/variants", tags=["variants"])


@router.get("/{variant_id}")
def get_variant(variant_id: uuid.UUID, db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    return ser.variant_detail(db, cat.get_variant_or_404(db, variant_id))


@router.patch("/{variant_id}")
def update_variant(variant_id: uuid.UUID, body: VariantPatch, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    changes = {k: val for k, val in body.model_dump(exclude_unset=True).items() if getattr(v, k) != val}
    for k, val in changes.items():
        setattr(v, k, val)
    if {"listing_url", "sale_unit", "sale_unit_quantity", "variant_key", "configuration"} & changes.keys():
        cat.mark_reassessing(db, v, "Listing details changed", p)
    audit(db, p, "variant.updated", "variant", v.id, {"fields": sorted(changes)})
    db.commit()
    return ser.variant_detail(db, v)


@router.delete("/{variant_id}")
def delete_variant(variant_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    if v.status in (VariantStatus.eligible.value, VariantStatus.reassessing.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "Retire a published variant instead of deleting it")
    if len(v.product.variants) == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "A product needs at least one variant; delete the product instead")
    audit(db, p, "variant.deleted", "product", v.product_id, {"variant_id": str(v.id)})
    db.delete(v)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- facts
@router.post("/{variant_id}/dimensions", status_code=201)
def add_dimensions(variant_id: uuid.UUID, body: DimensionIn, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    d = cat.add_dimension_revision(db, v, body.model_dump(), p)
    db.commit()
    return ser.dimension(d)


@router.post("/{variant_id}/price-observations", status_code=201)
def add_price(variant_id: uuid.UUID, body: PriceIn, db: Session = Depends(get_db),
              p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    obs = cat.add_price_observation(db, v, body.model_dump(), p)
    db.commit()
    return ser.price(obs)


@router.post("/{variant_id}/link-checks", status_code=201)
def add_link_check(variant_id: uuid.UUID, body: LinkCheckIn, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    lc = cat.record_link_check(db, v, body.outcome, p, url=body.url, http_status=body.http_status, note=body.note)
    db.commit()
    return ser.link_check(lc)


@router.put("/{variant_id}/attributes")
def set_attributes(variant_id: uuid.UUID, body: list[AttributeIn], db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    seen = set()
    v.attributes.clear()
    db.flush()
    for a in body:
        key = (a.key, a.value.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        v.attributes.append(VariantAttribute(key=a.key, value=a.value.strip(), colour_hex=a.colour_hex,
                                             source=a.source, verified=a.verified, confidence=a.confidence,
                                             created_by=p.user_id))
    audit(db, p, "attributes.set", "variant", v.id, {"count": len(seen)})
    db.commit()
    return ser.variant_detail(db, v)["attributes"]


@router.put("/{variant_id}/room-uses")
def set_room_uses(variant_id: uuid.UUID, body: list[RoomUseIn], db: Session = Depends(get_db),
                  p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    wanted = {(u.room_type, u.use_tag.strip() or "general") for u in body}
    if wanted != {(r.room_type, r.use_tag) for r in v.room_uses}:
        v.room_uses.clear()
        db.flush()
        for rt, tag in wanted:
            v.room_uses.append(VariantRoomUse(room_type=rt, use_tag=tag))
        db.flush()
        cat.reassess_after_value_change(db, v, "Room uses changed", p)
    audit(db, p, "room_uses.set", "variant", v.id)
    db.commit()
    return [{"room_type": r.room_type, "use_tag": r.use_tag} for r in v.room_uses]


@router.put("/{variant_id}/set-components")
def set_components(variant_id: uuid.UUID, body: list[SetComponentIn], db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    v.set_components.clear()
    db.flush()
    for n, c in enumerate(body):
        v.set_components.append(SetComponent(name=c.name, category_id=c.category_id, quantity=c.quantity,
                                             width_m=c.width_m, depth_m=c.depth_m, height_m=c.height_m,
                                             notes=c.notes, sort_order=n))
    db.flush()
    cat.mark_reassessing(db, v, "Set contents changed", p)
    audit(db, p, "set_components.set", "variant", v.id, {"count": len(body)})
    db.commit()
    return [ser.set_component(c) for c in v.set_components]


# --------------------------------------------------------------------------- admission
@router.get("/{variant_id}/admission")
def admission_conditions(variant_id: uuid.UUID, db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    v = cat.get_variant_or_404(db, variant_id)
    results = cat.evaluate_variant(db, v)
    return {"status": v.status, "conditions": [r.as_dict() for r in results],
            "all_required_pass": all(r.passed for r in results if r.required)}


@router.post("/{variant_id}/submit")
def submit(variant_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    cat.submit_for_review(db, v, p)
    db.commit()
    return {"status": v.status}


@router.post("/{variant_id}/admission-reviews", status_code=201)
def review(variant_id: uuid.UUID, body: AdmissionReviewIn, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    r = cat.apply_admission_review(db, v, body.decision, body.comment, p)
    db.commit()
    return {"status": v.status, "review": ser.admission_review(r)}


@router.post("/{variant_id}/publish")
def publish(variant_id: uuid.UUID, body: PublishIn, db: Session = Depends(get_db),
            p: Principal = Depends(require_roles(*EDITORS))):
    """'Add to catalogue' in one step: approve the 3D asset (if given), then admit the variant.

    Both decisions are still recorded separately, because eligibility and asset
    qualification are different states. If admission fails, the asset approval is
    rolled back too, so nothing half-published is left behind.
    """
    v = cat.get_variant_or_404(db, variant_id)
    if body.asset_id:
        if p.user.role not in {r.value for r in ASSET_REVIEWERS} | {UserRole.admin.value}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot approve 3D assets")
        a = get_asset_or_404(db, body.asset_id)
        if a.variant_id != v.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Asset belongs to another variant")
        if a.status != "qualified":
            review_asset(db, a, "approve", body.checklist, body.comment, True, p)
    try:
        cat.apply_admission_review(db, v, "approve", body.comment, p)
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    return ser.variant_detail(db, v)


@router.post("/{variant_id}/retire")
def retire(variant_id: uuid.UUID, body: RetireIn, db: Session = Depends(get_db),
           p: Principal = Depends(require_roles(*EDITORS))):
    v = cat.get_variant_or_404(db, variant_id)
    cat.retire_variant(db, v, body.reason, p)
    db.commit()
    return {"status": v.status}
