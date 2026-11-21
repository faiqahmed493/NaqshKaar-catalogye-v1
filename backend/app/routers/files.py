"""Signed file delivery. URLs come from security.file_url() and expire; no session needed,
so <img> tags, the Three.js loader and remote workers can all use them."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import StoredFile
from ..security import verify_file_signature
from ..storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}")
def get_file(file_id: uuid.UUID, exp: int = Query(...), sig: str = Query(...), download: bool = False,
             db: Session = Depends(get_db)):
    if not verify_file_signature(str(file_id), exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link expired or invalid")
    f = db.get(StoredFile, file_id)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    headers = {"Cache-Control": "private, max-age=3600"}
    if download and f.original_filename:
        headers["Content-Disposition"] = f'attachment; filename="{f.original_filename}"'
    store = get_storage()
    path = store.local_path(f.storage_key)
    if path is not None:
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage")
        return FileResponse(path, media_type=f.mime_type, headers=headers)
    return Response(store.get(f.storage_key), media_type=f.mime_type, headers=headers)
