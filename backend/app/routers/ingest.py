"""Ingest API for your data-collection software (scope: ingest).

POST /api/ingest/products          upsert one product with its variants (idempotent)
POST /api/ingest/products/batch    up to 50 products; each succeeds or fails on its own
POST /api/ingest/variants/{id}/price-observations   refresh-only price push
POST /api/ingest/variants/{id}/images               upload image files directly (multipart)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..db import get_db
from ..deps import Principal, require_api_key
from ..enums import ImageRole, ViewAngle
from ..schemas import IngestPrice, IngestProduct
from ..services import catalogue as cat
from ..services.images import add_image
from ..services.ingest import upsert_product

router = APIRouter(prefix="/api/ingest", tags=["ingest"])
ingest_key = require_api_key("ingest")


@router.post("/products")
def ingest_product(body: IngestProduct, db: Session = Depends(get_db), p: Principal = Depends(ingest_key)):
    report = upsert_product(db, body, p)
    db.commit()
    return report


@router.post("/products/batch")
def ingest_batch(body: list[dict], db: Session = Depends(get_db), p: Principal = Depends(ingest_key)):
    if len(body) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At most 50 products per batch")
    results = []
    for n, raw in enumerate(body):
        try:
            item = IngestProduct.model_validate(raw)
            report = upsert_product(db, item, p)
            db.commit()
            results.append({"index": n, "ok": True, **report})
        except ValidationError as exc:
            db.rollback()
            results.append({"index": n, "ok": False, "error": exc.errors(include_url=False)})
        except HTTPException as exc:
            db.rollback()
            results.append({"index": n, "ok": False, "error": exc.detail})
    return {"results": results, "ok": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results)}


@router.post("/variants/{variant_id}/price-observations", status_code=201)
def ingest_price(variant_id: uuid.UUID, body: IngestPrice, db: Session = Depends(get_db),
                 p: Principal = Depends(ingest_key)):
    v = cat.get_variant_or_404(db, variant_id)
    obs = cat.add_price_observation(db, v, body.model_dump(), p, source_kind="api")
    db.commit()
    return ser.price(obs)


@router.post("/variants/{variant_id}/images", status_code=201)
async def ingest_images(variant_id: uuid.UUID, files: list[UploadFile] = File(...),
                        view_angle: ViewAngle = Form(default=ViewAngle.unknown),
                        role: ImageRole = Form(default=ImageRole.gallery),
                        db: Session = Depends(get_db), p: Principal = Depends(ingest_key)):
    v = cat.get_variant_or_404(db, variant_id)
    out = []
    for f in files[:12]:
        img, created = add_image(db, v.product, await f.read(), f.filename or "image", variant_id=v.id, user_id=None,
                                 role=role.value, view_angle=view_angle.value)
        out.append({"created": created, **ser.image(img)})
    db.commit()
    return out
