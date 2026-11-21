"""Read API for the Naqshkaar planner (scope: catalogue_read, or a signed-in user).

Only `eligible` variants are selectable. `asset_ready` is reported separately:
a variant can be eligible while its 3D asset is still being prepared (FR-3D-006
makes the planner block final designs that use it).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, user_or_api_key
from ..security import file_url

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])
reader = user_or_api_key("catalogue_read")


def _row(r) -> dict:
    m = dict(r._mapping)
    for k in ("width_m", "depth_m", "height_m"):
        m[k] = float(m[k]) if m[k] is not None else None
    m["price_pkr"] = f"{m['price_pkr']:.2f}" if isinstance(m["price_pkr"], Decimal) else m["price_pkr"]
    for k in ("variant_id", "product_id", "retailer_id", "dimension_id", "asset_id", "glb_file_id",
              "price_observation_id"):
        m[k] = str(m[k]) if m[k] is not None else None
    m["price_checked_at"] = m["price_checked_at"].isoformat() if m["price_checked_at"] else None
    m["glb_url"] = file_url(m.pop("glb_file_id")) if m.get("asset_ready") else None
    return m


@router.get("/variants")
def catalogue_variants(
    eligible_only: bool = True, asset_ready: bool | None = None, room_type: str | None = None,
    category: str | None = None, max_price_pkr: Decimal | None = None,
    max_width_m: float | None = None, max_depth_m: float | None = None, max_height_m: float | None = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _: Principal = Depends(reader),
):
    where, params = ["true"], {"limit": limit, "offset": offset}
    if eligible_only:
        where.append("c.eligible")
    if asset_ready is not None:
        where.append("c.asset_ready = :asset_ready")
        params["asset_ready"] = asset_ready
    if room_type:
        where.append("EXISTS (SELECT 1 FROM variant_room_use u WHERE u.variant_id = c.variant_id "
                     "AND u.room_type = CAST(:room_type AS room_type))")
        params["room_type"] = room_type
    if category:
        where.append("c.category_code = :category")
        params["category"] = category
    if max_price_pkr is not None:
        where.append("c.price_pkr <= :max_price")
        params["max_price"] = max_price_pkr
    for col, val in (("width_m", max_width_m), ("depth_m", max_depth_m), ("height_m", max_height_m)):
        if val is not None:
            where.append(f"c.{col} <= :{col}")
            params[col] = val
    sql = f"SELECT * FROM v_catalogue_variant c WHERE {' AND '.join(where)} ORDER BY c.product_name LIMIT :limit OFFSET :offset"
    rows = db.execute(text(sql), params).all()
    return {"items": [_row(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/variants/{variant_id}")
def catalogue_variant(variant_id: str, db: Session = Depends(get_db), _: Principal = Depends(reader)):
    r = db.execute(text("SELECT * FROM v_catalogue_variant WHERE variant_id = CAST(:id AS uuid)"), {"id": variant_id}).first()
    if not r:
        return {"found": False}
    out = _row(r)
    out["attributes"] = [dict(x._mapping) for x in db.execute(text(
        "SELECT key, value, colour_hex, verified FROM variant_attribute WHERE variant_id = CAST(:id AS uuid)"),
        {"id": variant_id})]
    out["room_uses"] = [dict(x._mapping) for x in db.execute(text(
        "SELECT room_type, use_tag FROM variant_room_use WHERE variant_id = CAST(:id AS uuid)"), {"id": variant_id})]
    out["set_components"] = [
        {**dict(x._mapping), **{k: float(x._mapping[k]) if x._mapping[k] is not None else None
                                for k in ("width_m", "depth_m", "height_m")}}
        for x in db.execute(text("SELECT name, quantity, width_m, depth_m, height_m FROM set_component "
                                 "WHERE variant_id = CAST(:id AS uuid) ORDER BY sort_order"), {"id": variant_id})]
    return {"found": True, **out}
