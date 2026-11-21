"""File storage: local disk (default) or any S3-compatible service (AWS S3, MinIO, Cloudflare R2)."""
from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import StoredFile

settings = get_settings()

EXTENSIONS = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg",
    "model/gltf-binary": ".glb", "application/json": ".json", "text/plain": ".txt",
}


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("storage key escapes the storage root")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def local_path(self, key: str) -> Path | None:
        return self._path(key)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass


class S3Storage:
    def __init__(self):
        import boto3  # optional dependency
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url or None, region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
        )

    def put(self, key: str, data: bytes, mime: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def local_path(self, key: str) -> Path | None:
        return None

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> LocalStorage | S3Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_root)


def save_bytes(db: Session, data: bytes, mime: str, *, prefix: str, filename: str | None = None,
               user_id: uuid.UUID | None = None, dedupe: bool = False) -> StoredFile:
    """Store bytes and register them. With dedupe=True an identical existing file is reused."""
    digest = hashlib.sha256(data).hexdigest()
    if dedupe:
        existing = db.scalar(select(StoredFile).where(StoredFile.sha256 == digest, StoredFile.mime_type == mime))
        if existing:
            return existing
    now = datetime.now(timezone.utc)
    ext = EXTENSIONS.get(mime) or mimetypes.guess_extension(mime) or ""
    key = f"{prefix}/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"
    get_storage().put(key, data, mime)
    f = StoredFile(storage_key=key, mime_type=mime, size_bytes=len(data), sha256=digest,
                   original_filename=filename, created_by=user_id)
    db.add(f)
    db.flush()
    return f


def read_bytes(f: StoredFile) -> bytes:
    return get_storage().get(f.storage_key)
