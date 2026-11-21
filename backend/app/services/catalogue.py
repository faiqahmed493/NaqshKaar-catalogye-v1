"""Variant lifecycle: dimensions, prices, link checks, admission and reassessment.

Status flow (FR-CAT-009, FR-CAT-013):
    draft ──submit──▶ in_review ──approve──▶ eligible
      ▲                  │ reject                │ value changed
      └─request_changes──┘──────▶ ineligible     ▼
                                              reassessing ──approve──▶ eligible
Only `eligible` variants are selectable by the Naqshkaar planner.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import Principal
from ..domain import admission_rules as rules
from ..domain.units import AXES, UnitError, entered_from_payload
from ..enums import AssetStatus, ObservationOutcome, VariantStatus
from ..models import (AdmissionReview, Asset3D, Category, LinkCheck, PriceObservation, Product, ProductImage,
                      ProductVariant, SetComponent, VariantDimension)
from .audit import audit

settings = get_settings()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- lookups
def current_dimension(db: Session, variant_id: uuid.UUID) -> VariantDimension | None:
    return db.scalar(select(VariantDimension).where(VariantDimension.variant_id == variant_id,
                                                    VariantDimension.is_current.is_(True)))


def latest_price(db: Session, variant_id: uuid.UUID) -> PriceObservation | None:
    return db.scalar(select(PriceObservation)
                     .where(PriceObservation.variant_id == variant_id,
                            PriceObservation.outcome == ObservationOutcome.success.value)
                     .order_by(PriceObservation.checked_at.desc(), PriceObservation.created_at.desc()).limit(1))


def latest_link_check(db: Session, variant_id: uuid.UUID) -> LinkCheck | None:
    return db.scalar(select(LinkCheck).where(LinkCheck.variant_id == variant_id)
                     .order_by(LinkCheck.checked_at.desc()).limit(1))


def variant_images(db: Session, variant: ProductVariant) -> list[ProductImage]:
    return list(db.scalars(select(ProductImage).where(
        ProductImage.product_id == variant.product_id,
        (ProductImage.variant_id == variant.id) | (ProductImage.variant_id.is_(None)),
    ).order_by(ProductImage.sort_order, ProductImage.created_at)))


def effective_listing_url(variant: ProductVariant) -> str | None:
    return variant.listing_url or variant.product.listing_url


def get_variant_or_404(db: Session, variant_id: uuid.UUID) -> ProductVariant:
    v = db.get(ProductVariant, variant_id)
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    return v


# --------------------------------------------------------------------------- admission facts
def gather_facts(db: Session, v: ProductVariant) -> rules.VariantFacts:
    p: Product = v.product
    cat: Category | None = p.category
    dim = current_dimension(db, v.id)
    price = latest_price(db, v.id)
    link = latest_link_check(db, v.id)
    siblings = db.scalar(select(func.count()).select_from(ProductVariant)
                         .where(ProductVariant.product_id == p.id, ProductVariant.status != VariantStatus.retired.value))
    comps = list(db.scalars(select(SetComponent).where(SetComponent.variant_id == v.id)))
    return rules.VariantFacts(
        retailer_name=p.retailer.name if p.retailer else None,
        product_name=p.name,
        variant_label=v.variant_label,
        sibling_variant_count=siblings or 1,
        category_code=cat.code if cat else None,
        category_supported=bool(cat and cat.is_supported),
        category_is_group_only=bool(cat and cat.parent_id is None),
        room_use_count=len(v.room_uses),
        sale_unit=v.sale_unit,
        sale_unit_quantity=v.sale_unit_quantity,
        listing_url=effective_listing_url(v),
        latest_link_check_url=link.url if link else None,
        latest_link_check_outcome=link.outcome if link else None,
        dimension=rules.DimensionFacts(dim.kind, dim.width_m, dim.depth_m, dim.height_m, dim.source_ref,
                                       dim.source_text) if dim else None,
        price=rules.PriceFacts(price.price_pkr, price.sale_unit, price.availability, price.source_url,
                               price.checked_at) if price else None,
        images=[rules.ImageFacts(i.reviewed, i.depicts_variant) for i in variant_images(db, v)],
        set_component_count=len(comps),
        set_components_missing_dims=sum(1 for c in comps if not (c.width_m and c.depth_m and c.height_m)),
    )


def evaluate_variant(db: Session, v: ProductVariant) -> list[rules.ConditionResult]:
    return rules.evaluate(gather_facts(db, v), price_stale_days=settings.price_stale_days)


def mark_reassessing(db: Session, v: ProductVariant, reason: str, actor: Principal | None) -> None:
    """FR-CAT-013: a changed eligible entry is withheld from new selections until requalified."""
    if v.status == VariantStatus.eligible.value:
        v.status = VariantStatus.reassessing.value
        v.status_reason = reason
        audit(db, actor, "variant.reassessing", "variant", v.id, {"reason": reason})


def reassess_after_value_change(db: Session, v: ProductVariant, reason: str, actor: Principal | None) -> None:
    """Re-run the automated conditions. If the eligible entry still passes, it stays eligible."""
    if v.status != VariantStatus.eligible.value:
        return
    db.flush()
    failed = rules.failed_required(evaluate_variant(db, v))
    if failed:
        mark_reassessing(db, v, f"{reason}: " + "; ".join(f.label for f in failed), actor)


# --------------------------------------------------------------------------- dimensions
def add_dimension_revision(db: Session, v: ProductVariant, data: dict[str, Any], actor: Principal) -> VariantDimension:
    """Record a new dimension revision. Values may be partial (unknown stays NULL).

    data: {kind, width|depth|height: {value, unit[, inches]} or width_m.., source_text, source_axis_order,
           source_ref, observed_at, note}
    """
    metres: dict[str, Decimal | None] = {}
    entered: dict[str, Any] = {}
    units_seen: set[str] = set()
    try:
        for axis in AXES:
            if data.get(f"{axis}_m") not in (None, ""):
                metres[axis] = Decimal(str(data[f"{axis}_m"]))
                if metres[axis] <= 0:
                    raise UnitError(f"{axis} must be greater than zero")
                entered[axis] = {"value": str(metres[axis]), "unit": "m"}
                units_seen.add("m")
                continue
            e = entered_from_payload(data.get(axis))
            metres[axis] = e.metres() if e else None
            if e:
                entered[axis] = e.as_json()
                units_seen.add(e.unit)
    except UnitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    prev = current_dimension(db, v.id)
    same = prev is not None and prev.kind == data.get("kind", "assembled") and all(
        (getattr(prev, f"{a}_m") or None) == (metres[a].quantize(Decimal("0.0001")) if metres[a] else None)
        for a in AXES)
    if same:
        # Identical values: refresh evidence on the existing revision rather than invalidating assets.
        prev.source_text = data.get("source_text") or prev.source_text
        prev.source_ref = data.get("source_ref") or prev.source_ref
        prev.observed_at = data.get("observed_at") or prev.observed_at
        return prev

    max_rev = db.scalar(select(func.max(VariantDimension.revision)).where(VariantDimension.variant_id == v.id)) or 0
    if prev:
        prev.is_current = False
        db.flush()
    dim = VariantDimension(
        variant_id=v.id, revision=max_rev + 1, kind=data.get("kind") or "assembled",
        width_m=metres["width"], depth_m=metres["depth"], height_m=metres["height"],
        entered_unit=units_seen.pop() if len(units_seen) == 1 else None, entered_values=entered,
        source_text=data.get("source_text"), source_axis_order=data.get("source_axis_order"),
        source_ref=data.get("source_ref"), observed_at=data.get("observed_at") or now_utc(),
        is_current=True, note=data.get("note"), recorded_by=actor.user_id,
    )
    db.add(dim)
    v.dimension_revision = dim.revision
    db.flush()

    # Assets qualified or pending against the old revision no longer qualify (FR-3D-005 scenario 2).
    if prev:
        stale = db.execute(update(Asset3D)
                           .where(Asset3D.variant_id == v.id,
                                  Asset3D.status.in_([AssetStatus.qualified.value, AssetStatus.in_review.value,
                                                      AssetStatus.needs_correction.value]))
                           .values(status=AssetStatus.stale.value, is_selected=False)
                           .execution_options(synchronize_session="fetch"))
        if stale.rowcount:
            audit(db, actor, "assets.stale", "variant", v.id, {"count": stale.rowcount, "dimension_revision": dim.revision})
        mark_reassessing(db, v, f"Dimensions changed (revision {dim.revision}); review required", actor)
    audit(db, actor, "dimension.added", "variant", v.id, {"revision": dim.revision})
    return dim


# --------------------------------------------------------------------------- prices
def add_price_observation(db: Session, v: ProductVariant, data: dict[str, Any], actor: Principal,
                          source_kind: str = "manual") -> PriceObservation:
    outcome = data.get("outcome") or ObservationOutcome.success.value
    price = data.get("price_pkr")
    if outcome == ObservationOutcome.failed.value:
        if not data.get("failure_reason"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A failed check needs a failure_reason")
        price = None
    elif price is not None:
        price = Decimal(str(price)).quantize(Decimal("0.01"))
        if price < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Price cannot be negative")
    obs = PriceObservation(
        variant_id=v.id, outcome=outcome, price_pkr=price,
        compare_at_price_pkr=data.get("compare_at_price_pkr"),
        sale_unit=data.get("sale_unit") or v.sale_unit,
        availability=data.get("availability") or "unknown",
        includes_delivery=data.get("includes_delivery"),
        source_url=data.get("source_url") or effective_listing_url(v),
        source_kind=source_kind, checked_at=data.get("checked_at") or now_utc(),
        failure_reason=data.get("failure_reason"), raw_payload=data.get("raw_payload"),
        recorded_by=actor.user_id,
    )
    db.add(obs)
    db.flush()
    audit(db, actor, "price.observed", "variant", v.id,
          {"outcome": outcome, "price_pkr": str(price) if price is not None else None})
    if outcome == ObservationOutcome.success.value:
        reassess_after_value_change(db, v, "Price or availability changed", actor)
    # A failed refresh changes nothing: the old observation keeps its own check time.
    return obs


# --------------------------------------------------------------------------- link checks
def record_link_check(db: Session, v: ProductVariant, outcome: str, actor: Principal, *, url: str | None = None,
                      http_status: int | None = None, note: str | None = None) -> LinkCheck:
    target = url or effective_listing_url(v)
    if not target:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Variant has no listing URL to check")
    lc = LinkCheck(variant_id=v.id, url=target, outcome=outcome, http_status=http_status, note=note,
                   checked_by=actor.user_id)
    db.add(lc)
    db.flush()
    audit(db, actor, "link.checked", "variant", v.id, {"outcome": outcome})
    if outcome != "ok":
        mark_reassessing(db, v, f"Purchase link check: {outcome}", actor)  # FR-CAT-008 scenario 2
    return lc


# --------------------------------------------------------------------------- review actions
def submit_for_review(db: Session, v: ProductVariant, actor: Principal) -> None:
    if v.status in (VariantStatus.eligible.value, VariantStatus.retired.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Variant is {v.status}")
    v.status = VariantStatus.in_review.value
    v.status_reason = None
    audit(db, actor, "variant.submitted", "variant", v.id)


def apply_admission_review(db: Session, v: ProductVariant, decision: str, comment: str | None,
                           actor: Principal) -> AdmissionReview:
    if actor.user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admission needs a human reviewer")
    if v.status == VariantStatus.retired.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Variant is retired")
    results = evaluate_variant(db, v)
    if decision == "approve" and not rules.all_required_pass(results):
        failed = rules.failed_required(results)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {
            "message": "Cannot admit: some required conditions fail.",
            "failed": [f.as_dict() for f in failed],
        })
    dim = current_dimension(db, v.id)
    price = latest_price(db, v.id)
    review = AdmissionReview(variant_id=v.id, reviewer_id=actor.user.id, decision=decision,
                             conditions=[r.as_dict() for r in results], dimension_id=dim.id if dim else None,
                             price_observation_id=price.id if price else None, comment=comment)
    db.add(review)
    if decision == "approve":
        v.status = VariantStatus.eligible.value
        v.eligible_since = v.eligible_since or now_utc()
        v.status_reason = None
    elif decision == "reject":
        v.status = VariantStatus.ineligible.value
        v.status_reason = comment or "Rejected by reviewer"
    else:
        v.status = VariantStatus.draft.value
        v.status_reason = comment or "Changes requested"
    audit(db, actor, f"admission.{decision}", "variant", v.id, {"comment": comment})
    return review


def retire_variant(db: Session, v: ProductVariant, reason: str | None, actor: Principal) -> None:
    v.status = VariantStatus.retired.value
    v.status_reason = reason or "Retired"
    db.execute(update(Asset3D).where(Asset3D.variant_id == v.id).values(is_selected=False))
    audit(db, actor, "variant.retired", "variant", v.id, {"reason": reason})
