"""Product image intake: PNG, JPEG, WebP and SVG (FR-CAT-006).

Every upload is decoded before it is accepted, so an unreadable file is rejected
instead of stored. Three files are kept per image: the original, a normalised PNG
(SVG rasterised, EXIF rotation applied, longest side capped) that the 3D engines
consume, and a small thumbnail for the UI.
"""
from __future__ import annotations

import io
import uuid

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Product, ProductImage, StoredFile
from ..storage import save_bytes

settings = get_settings()
Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression bombs

FORMAT_MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}


class ImageRejected(HTTPException):
    def __init__(self, filename: str, reason: str):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{filename}: {reason}")


def _looks_like_svg(data: bytes) -> bool:
    head = data[:2048].lstrip().lower()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:8192].lower())


def _rasterise_svg(data: bytes, max_side: int) -> Image.Image:
    try:
        import cairosvg
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise RuntimeError("cairosvg is required for SVG uploads") from exc
    png = cairosvg.svg2png(bytestring=data, output_width=max_side, unsafe=False)
    img = Image.open(io.BytesIO(png))
    img.load()
    return img


def decode(data: bytes, filename: str) -> tuple[str, Image.Image]:
    """Return (format, decoded RGBA image) or raise ImageRejected."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise ImageRejected(filename, "file is empty")
    if len(data) > max_bytes:
        raise ImageRejected(filename, f"file is larger than {settings.max_upload_mb} MB")
    if _looks_like_svg(data):
        try:
            img = _rasterise_svg(data, settings.processed_image_max_side)
        except Exception as exc:  # noqa: BLE001 - any parser failure means unreadable
            raise ImageRejected(filename, f"SVG could not be rendered ({exc.__class__.__name__})") from exc
        return "svg", img.convert("RGBA")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").lower()
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageRejected(filename, "not a readable image") from exc
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg", "webp"):
        raise ImageRejected(filename, f"format '{fmt or 'unknown'}' is not accepted; use PNG, JPEG, WebP or SVG")
    img = ImageOps.exif_transpose(img)
    return fmt, img.convert("RGBA")


def _png_bytes(img: Image.Image, max_side: int) -> bytes:
    im = img.copy()
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _thumb_bytes(img: Image.Image, side: int) -> bytes:
    im = img.copy()
    im.thumbnail((side, side), Image.LANCZOS)
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[-1])
    buf = io.BytesIO()
    bg.save(buf, format="WEBP", quality=82)
    return buf.getvalue()


def add_image(db: Session, product: Product, data: bytes, filename: str, *, variant_id: uuid.UUID | None,
              user_id: uuid.UUID | None, role: str = "gallery", view_angle: str = "unknown",
              source_url: str | None = None, reviewed: bool = False,
              depicts_variant: bool | None = None) -> tuple[ProductImage, bool]:
    """Validate, store and register one image. Returns (image, created). Duplicates on the same product are reused."""
    fmt, img = decode(data, filename)
    original = save_bytes(db, data, FORMAT_MIME[fmt], prefix="images/original", filename=filename,
                          user_id=user_id, dedupe=True)
    existing = db.scalar(select(ProductImage).where(ProductImage.product_id == product.id,
                                                    ProductImage.file_id == original.id))
    if existing:
        return existing, False
    processed = save_bytes(db, _png_bytes(img, settings.processed_image_max_side), "image/png",
                           prefix="images/processed", filename=f"{filename}.png", user_id=user_id)
    thumb = save_bytes(db, _thumb_bytes(img, settings.thumbnail_side), "image/webp",
                       prefix="images/thumb", filename=f"{filename}.webp", user_id=user_id)
    count = len(product.images)
    pi = ProductImage(
        product_id=product.id, variant_id=variant_id, file_id=original.id, processed_file_id=processed.id,
        thumbnail_file_id=thumb.id, original_format=fmt, width_px=img.width, height_px=img.height,
        role=role if count else "primary", view_angle=view_angle, source_url=source_url, sort_order=count,
        created_by=user_id, reviewed=reviewed, depicts_variant=depicts_variant,
        reviewed_by=user_id if reviewed else None,
    )
    db.add(pi)
    db.flush()
    product.images.append(pi)
    return pi, True


def processed_file(db: Session, image: ProductImage) -> StoredFile:
    return db.get(StoredFile, image.processed_file_id or image.file_id)
