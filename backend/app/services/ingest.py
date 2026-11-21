"""Ingest API for the data-collection software (and CSV imports).

Idempotent upsert keyed on (retailer slug, external_ref) for products and
(variant_key, configuration) for variants. Re-posting the same product:
  * adds a new dated price observation every time (history is kept)
  * adds a dimension revision only when the values actually changed
  * skips images already stored (sha256)
Records arrive as drafts. Nothing pushed by software becomes selectable without
a human admission review (DEC-CAT-01), and pushed attributes start unverified.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import Principal
from ..models import (Category, Product, ProductVariant, Retailer, SetComponent, VariantAttribute,
                      VariantRoomUse)
from ..schemas import IngestProduct, IngestVariant
from . import catalogue as cat
from .audit import audit
from .images import ImageRejected, add_image

log = logging.getLogger("naqshkaar.ingest")
settings = get_settings()


def _retailer(db: Session, payload: IngestProduct) -> Retailer:
    r = db.scalar(select(Retailer).where(Retailer.slug == payload.retailer.slug))
    if r:
        return r
    if not settings.ingest_auto_create_retailer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Unknown retailer '{payload.retailer.slug}'. Create it in the studio first.")
    r = Retailer(slug=payload.retailer.slug, name=payload.retailer.name or payload.retailer.slug,
                 website_url=payload.retailer.website_url, city=payload.retailer.city)
    db.add(r)
    db.flush()
    return r


def _fetch(url: str) -> bytes:
    limit = settings.max_upload_mb * 1024 * 1024
    with httpx.Client(timeout=settings.ingest_image_timeout_seconds, follow_redirects=True,
                      headers={"User-Agent": "NaqshkaarCatalogueStudio/1.0"}) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError("image too large")
                chunks.append(chunk)
    return b"".join(chunks)


def _apply_variant(db: Session, product: Product, data: IngestVariant, actor: Principal,
                   report: dict[str, Any]) -> ProductVariant:
    v = db.scalar(select(ProductVariant).where(ProductVariant.product_id == product.id,
                                               ProductVariant.variant_key == data.variant_key,
                                               ProductVariant.configuration == data.configuration))
    created = v is None
    if created:
        v = ProductVariant(product_id=product.id, variant_key=data.variant_key, configuration=data.configuration)
        db.add(v)
        product.variants.append(v)
    changed_identity = False
    for field in ("variant_label", "listing_url", "sale_unit", "sale_unit_quantity", "placement_type"):
        new = getattr(data, field)
        if new is not None and getattr(v, field) != new:
            changed_identity = changed_identity or (not created and field in ("listing_url", "sale_unit",
                                                                              "sale_unit_quantity"))
            setattr(v, field, new)
    db.flush()
    if changed_identity:
        cat.mark_reassessing(db, v, "Listing details changed by collector", actor)

    if data.attributes:
        have = {(a.key, a.value.lower()) for a in v.attributes}
        for a in data.attributes:
            if (a.key, a.value.lower()) not in have:
                v.attributes.append(VariantAttribute(key=a.key, value=a.value, colour_hex=a.colour_hex,
                                                     source=a.source, verified=False, confidence=a.confidence))
    if data.room_uses:
        have_uses = {(u.room_type, u.use_tag) for u in v.room_uses}
        for u in data.room_uses:
            if (u.room_type, u.use_tag) not in have_uses:
                v.room_uses.append(VariantRoomUse(room_type=u.room_type, use_tag=u.use_tag))
    if data.set_components and not v.set_components:
        for n, c in enumerate(data.set_components):
            v.set_components.append(SetComponent(name=c.name, category_id=c.category_id, quantity=c.quantity,
                                                 width_m=c.width_m, depth_m=c.depth_m, height_m=c.height_m,
                                                 notes=c.notes, sort_order=n))
    db.flush()

    if data.dimensions:
        before = v.dimension_revision
        cat.add_dimension_revision(db, v, data.dimensions.model_dump(), actor)
        if v.dimension_revision != before:
            report["dimension_revisions"] += 1
    if data.price:
        cat.add_price_observation(db, v, data.price.model_dump(), actor, source_kind="api")
        report["price_observations"] += 1

    if data.images and settings.ingest_fetch_images:
        for img in data.images:
            try:
                raw = _fetch(str(img.url))
                _, was_new = add_image(db, product, raw, str(img.url).rsplit("/", 1)[-1][:120] or "image",
                                       variant_id=v.id, user_id=None, role=img.role, view_angle=img.view_angle,
                                       source_url=str(img.url), depicts_variant=img.depicts_variant)
                report["images_added" if was_new else "images_skipped"] += 1
            except (httpx.HTTPError, ValueError, ImageRejected) as exc:
                msg = exc.detail if isinstance(exc, ImageRejected) else str(exc)
                report["image_errors"].append({"url": str(img.url), "error": msg})
    report["variants"].append({"variant_key": v.variant_key, "configuration": v.configuration, "id": str(v.id),
                               "created": created, "status": v.status})
    return v


def upsert_product(db: Session, payload: IngestProduct, actor: Principal) -> dict[str, Any]:
    retailer = _retailer(db, payload)
    category_id = None
    if payload.category_code:
        c = db.scalar(select(Category).where(Category.code == payload.category_code))
        if not c:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown category_code '{payload.category_code}'")
        category_id = c.id
    product = db.scalar(select(Product).where(Product.retailer_id == retailer.id,
                                              Product.external_ref == payload.external_ref))
    created = product is None
    if created:
        product = Product(retailer_id=retailer.id, external_ref=payload.external_ref, name=payload.name, source="api")
        db.add(product)
    for field in ("name", "brand", "description", "listing_url", "retailer_product_ref"):
        val = getattr(payload, field)
        if val is not None:
            setattr(product, field, val)
    if category_id is not None:
        product.category_id = category_id
    db.flush()

    report: dict[str, Any] = {"product_id": str(product.id), "created": created, "variants": [],
                              "price_observations": 0, "dimension_revisions": 0, "images_added": 0,
                              "images_skipped": 0, "image_errors": []}
    for vdata in payload.variants:
        _apply_variant(db, product, vdata, actor, report)
    audit(db, actor, "ingest.product", "product", product.id,
          {"external_ref": payload.external_ref, "created": created})
    return report
