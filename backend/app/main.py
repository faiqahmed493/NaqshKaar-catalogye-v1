"""FastAPI application. Run:  uvicorn app.main:app --reload  (from backend/)."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import engine
from .routers import auth, catalogue, files, generation, ingest, products, reference, stats, variants, worker

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Prepares the Naqshkaar product catalogue: retailer variants, dated PKR prices, "
                "source-backed dimensions, images and qualified metric 3D assets.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, reference, products, variants, generation, worker, ingest, catalogue, files, stats):
    app.include_router(r.router)


@app.exception_handler(IntegrityError)
def integrity_error(_: Request, exc: IntegrityError):
    # Surface database rule violations (unique keys, CHECK constraints) as readable 409s.
    msg = str(exc.orig).split("\n")[0] if exc.orig else "database constraint violated"
    return JSONResponse(status_code=409, content={"detail": f"Rejected by a database rule: {msg}"})


@app.get("/api/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "app": settings.app_name, "storage": settings.storage_backend}
