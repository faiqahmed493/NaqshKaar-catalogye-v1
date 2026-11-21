from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from .. import serializers as ser
from ..config import get_settings
from ..db import get_db
from ..deps import EDITORS, Principal, any_user, require_roles
from ..enums import ImageRole, ViewAngle
from ..models import (Asset3D, Category, Product, ProductImage, ProductVariant, Retailer, SetComponent,
                      VariantAttribute, VariantDimension, VariantRoomUse)
from ..schemas import ImagePatch, ProductIn, ProductPatch, VariantIn
from ..services import catalogue as cat
from ..services.audit import audit
from ..services.images import add_image

router = APIRouter(prefix="/api", tags=["products"])
settings = get_settings()


def get_product_or_404(db: Session, product_id: uuid.UUID) -> Product:
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return p


def apply_variant_extras(db: Session, v: ProductVariant, body: VariantIn, p: Principal) -> None:
    if body.dimensions:
        cat.add_dimension_revision(db, v, body.dimensions.model_dump(), p)
    if body.price:
        cat.add_price_observation(db, v, body.price.model_dump(), p)
    for a in body.attributes:
        v.attributes.append(VariantAttribute(key=a.key, value=a.value, colour_hex=a.colour_hex, source=a.source,
                                             verified=a.verified, confidence=a.confidence, created_by=p.user_id))
    for u in {(u.room_type, u.use_tag) for u in body.room_uses}:
        v.room_uses.append(VariantRoomUse(room_type=u[0], use_tag=u[1]))
    for n, c in enumerate(body.set_components):
        v.set_components.append(SetComponent(name=c.name, category_id=c.category_id, quantity=c.quantity,
                                             width_m=c.width_m, depth_m=c.depth_m, height_m=c.height_m,
                                             notes=c.notes, sort_order=n))


def new_variant(db: Session, product: Product, body: VariantIn, p: Principal) -> ProductVariant:
    dup = db.scalar(select(ProductVariant).where(ProductVariant.product_id == product.id,
                                                 ProductVariant.variant_key == body.variant_key,
                                                 ProductVariant.configuration == body.configuration))
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Variant '{body.variant_key}' ({body.configuration}) already exists on this product")
    v = ProductVariant(product_id=product.id, variant_key=body.variant_key, variant_label=body.variant_label,
                       configuration=body.configuration, listing_url=body.listing_url, sale_unit=body.sale_unit,
                       sale_unit_quantity=body.sale_unit_quantity, sale_unit_note=body.sale_unit_note,
                       placement_type=body.placement_type, notes=body.notes, created_by=p.user_id)
    db.add(v)
    product.variants.append(v)
    db.flush()
    apply_variant_extras(db, v, body, p)
    audit(db, p, "variant.created", "variant", v.id)
    return v


@router.get("/products")
def list_products(
    q: str | None = None, retailer_id: uuid.UUID | None = None, category_id: int | None = None,
    status_: str | None = Query(default=None, alias="status"), asset: str | None = Query(default=None, pattern="^(ready|missing)$"),
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), _: Principal = Depends(any_user),
):
    stmt = select(Product)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.brand.ilike(like), Product.external_ref.ilike(like),
                              exists().where(ProductVariant.product_id == Product.id,
                                             or_(ProductVariant.variant_label.ilike(like),
                                                 ProductVariant.variant_key.ilike(like)))))
    if retailer_id:
        stmt = stmt.where(Product.retailer_id == retailer_id)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if status_:
        stmt = stmt.where(exists().where(ProductVariant.product_id == Product.id, ProductVariant.status == status_))
    if asset:
        # A variant is asset-ready when its selected qualified asset matches its current dimension revision.
        ready_variant = (
            select(ProductVariant.id)
            .join(VariantDimension, (VariantDimension.variant_id == ProductVariant.id)
                  & VariantDimension.is_current.is_(True))
            .join(Asset3D, (Asset3D.variant_id == ProductVariant.id) & Asset3D.is_selected.is_(True)
                  & (Asset3D.dimension_id == VariantDimension.id))
            .where(ProductVariant.product_id == Product.id)
            .correlate(Product)
            .exists()
        )
        stmt = stmt.where(ready_variant if asset == "ready" else ~ready_variant)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Product.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [ser.product_summary(db, p) for p in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/products", status_code=201)
def create_product(body: ProductIn, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    if not db.get(Retailer, body.retailer_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown retailer")
    if body.category_id and not db.get(Category, body.category_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
    product = Product(retailer_id=body.retailer_id, name=body.name.strip(), brand=body.brand,
                      category_id=body.category_id, description=body.description, listing_url=body.listing_url,
                      retailer_product_ref=body.retailer_product_ref, source="manual", created_by=p.user_id)
    db.add(product)
    db.flush()
    v = new_variant(db, product, body.variant, p)
    audit(db, p, "product.created", "product", product.id)
    db.commit()
    return {"product": ser.product_summary(db, product), "variant_id": str(v.id)}


@router.get("/products/{product_id}")
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db), _: Principal = Depends(any_user)):
    product = get_product_or_404(db, product_id)
    return {**ser.product_summary(db, product), "description": product.description,
            "retailer_product_ref": product.retailer_product_ref,
            "images": [ser.image(i) for i in product.images]}


@router.patch("/products/{product_id}")
def update_product(product_id: uuid.UUID, body: ProductPatch, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    product = get_product_or_404(db, product_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if getattr(product, k) != v}
    for k, v in changes.items():
        setattr(product, k, v)
    if {"name", "category_id", "listing_url", "retailer_id"} & changes.keys():
        for v in product.variants:
            cat.mark_reassessing(db, v, "Product details changed", p)
    audit(db, p, "product.updated", "product", product.id, {"fields": sorted(changes)})
    db.commit()
    return ser.product_summary(db, product)


@router.delete("/products/{product_id}")
def delete_product(product_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    product = get_product_or_404(db, product_id)
    if any(v.status in ("eligible", "reassessing") for v in product.variants):
        raise HTTPException(status.HTTP_409_CONFLICT, "Retire eligible variants first; published records are kept")
    audit(db, p, "product.deleted", "product", product.id, {"name": product.name})
    db.delete(product)
    db.commit()
    return {"ok": True}


@router.post("/products/{product_id}/variants", status_code=201)
def create_variant(product_id: uuid.UUID, body: VariantIn, db: Session = Depends(get_db),
                   p: Principal = Depends(require_roles(*EDITORS))):
    product = get_product_or_404(db, product_id)
    v = new_variant(db, product, body, p)
    db.commit()
    return ser.variant_detail(db, v)


# --------------------------------------------------------------------------- images
@router.post("/products/{product_id}/images", status_code=201)
async def upload_images(
    product_id: uuid.UUID,
    files: list[UploadFile] = File(..., description="PNG, JPEG, WebP or SVG; several allowed"),
    variant_id: uuid.UUID | None = Form(default=None, description="Omit to share the image with every variant"),
    role: ImageRole = Form(default=ImageRole.gallery),
    view_angle: ViewAngle = Form(default=ViewAngle.unknown),
    depicts_variant: bool = Form(default=True),
    db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS)),
):
    product = get_product_or_404(db, product_id)
    if variant_id and not any(v.id == variant_id for v in product.variants):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Variant does not belong to this product")
    if len(files) > settings.max_images_per_upload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"At most {settings.max_images_per_upload} files per upload")
    created, skipped = [], []
    for f in files:
        data = await f.read()
        img, was_new = add_image(db, product, data, f.filename or "upload", variant_id=variant_id, user_id=p.user_id,
                                 role=role.value if hasattr(role, "value") else role,
                                 view_angle=view_angle.value if hasattr(view_angle, "value") else view_angle,
                                 reviewed=True, depicts_variant=depicts_variant)
        (created if was_new else skipped).append(img)
    audit(db, p, "images.uploaded", "product", product.id, {"count": len(created)})
    db.commit()
    return {"created": [ser.image(i) for i in created], "duplicates": [ser.image(i) for i in skipped]}


def _image_or_404(db: Session, image_id: uuid.UUID) -> ProductImage:
    img = db.get(ProductImage, image_id)
    if not img:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return img


@router.patch("/images/{image_id}")
def update_image(image_id: uuid.UUID, body: ImagePatch, db: Session = Depends(get_db),
                 p: Principal = Depends(require_roles(*EDITORS))):
    img = _image_or_404(db, image_id)
    data = body.model_dump(exclude_unset=True)
    if data.pop("shared_with_all_variants", None):
        img.variant_id = None
    if "variant_id" in data:
        vid = data.pop("variant_id")
        if vid and not db.scalar(select(ProductVariant).where(ProductVariant.id == vid,
                                                              ProductVariant.product_id == img.product_id)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Variant does not belong to this product")
        img.variant_id = vid
    if data.get("role") == "primary":
        for other in db.scalars(select(ProductImage).where(ProductImage.product_id == img.product_id,
                                                           ProductImage.id != img.id, ProductImage.role == "primary")):
            other.role = "gallery"
    for k, v in data.items():
        setattr(img, k, v)
    if "depicts_variant" in data or "reviewed" in data:
        img.reviewed = True if data.get("reviewed", True) else False
        img.reviewed_by = p.user_id
    audit(db, p, "image.updated", "image", img.id, {k: str(v) for k, v in data.items()})
    db.commit()
    return ser.image(img)


@router.delete("/images/{image_id}")
def delete_image(image_id: uuid.UUID, db: Session = Depends(get_db), p: Principal = Depends(require_roles(*EDITORS))):
    img = _image_or_404(db, image_id)
    product = img.product
    audit(db, p, "image.deleted", "product", img.product_id, {"image_id": str(img.id)})
    db.delete(img)
    db.flush()
    for v in product.variants:
        cat.reassess_after_value_change(db, v, "Image removed", p)
    db.commit()
    return {"ok": True}
