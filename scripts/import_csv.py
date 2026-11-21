#!/usr/bin/env python3
"""Bulk-import a spreadsheet of listings through the ingest API.

    python scripts/import_csv.py --studio http://localhost:8000 --key nqk_... scripts/sample_products.csv

One row per variant. Columns (empty cells stay unknown, never zero):
  retailer_slug, retailer_name, external_ref, name, brand, category_code, listing_url,
  variant_key, variant_label, sale_unit, sale_unit_quantity,
  width, depth, height, unit, dimension_text, price_pkr, availability, checked_at,
  room_types (semicolon list), colour, material, style, image_urls (semicolon list), front_image_url
Rows sharing external_ref become variants of one product.
"""
import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from collections import OrderedDict


def length(row, axis):
    v = (row.get(axis) or "").strip()
    if not v:
        return None
    unit = (row.get("unit") or "").strip()
    if not unit:
        raise ValueError(f"{row.get('external_ref')}: '{axis}' has no unit column value")
    if unit == "ft_in":  # write as 6'8 or 6-8
        ft, _, inch = v.replace("'", "-").partition("-")
        return {"value": ft, "unit": "ft_in", "inches": inch or "0"}
    return {"value": v, "unit": unit}


def build(rows):
    products = OrderedDict()
    for r in rows:
        ref = r["external_ref"].strip()
        p = products.setdefault(ref, {
            "retailer": {"slug": r["retailer_slug"].strip(), "name": r.get("retailer_name") or None},
            "external_ref": ref, "name": r["name"].strip(), "brand": r.get("brand") or None,
            "category_code": r.get("category_code") or None, "listing_url": r.get("listing_url") or None,
            "variants": [],
        })
        dims = {k: length(r, k) for k in ("width", "depth", "height")}
        variant = {
            "variant_key": r.get("variant_key") or "default", "variant_label": r.get("variant_label") or None,
            "sale_unit": r.get("sale_unit") or None,
            "sale_unit_quantity": int(r["sale_unit_quantity"]) if (r.get("sale_unit_quantity") or "").strip() else None,
            "dimensions": ({"kind": "assembled", **dims, "source_text": r.get("dimension_text") or None,
                            "source_ref": r.get("listing_url") or None} if any(dims.values()) else None),
            "price": ({"price_pkr": r["price_pkr"].replace(",", ""), "availability": r.get("availability") or "unknown",
                       "checked_at": r.get("checked_at"), "source_url": r.get("listing_url") or None}
                      if (r.get("price_pkr") or "").strip() and (r.get("checked_at") or "").strip() else None),
            "room_uses": [{"room_type": t.strip()} for t in (r.get("room_types") or "").split(";") if t.strip()],
            "attributes": [{"key": k, "value": r[k].strip()} for k in ("colour", "material", "style") if (r.get(k) or "").strip()],
            "images": ([{"url": r["front_image_url"].strip(), "view_angle": "front", "role": "primary"}]
                       if (r.get("front_image_url") or "").strip() else [])
                      + [{"url": u.strip()} for u in (r.get("image_urls") or "").split(";") if u.strip()],
        }
        p["variants"].append(variant)
    return list(products.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--studio", default="http://localhost:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the JSON instead of sending it")
    ap.add_argument("csv_file")
    args = ap.parse_args()
    with open(args.csv_file, newline="", encoding="utf-8-sig") as fh:
        products = build(list(csv.DictReader(fh)))
    if args.dry_run:
        print(json.dumps(products, indent=2))
        return
    for start in range(0, len(products), 50):
        chunk = products[start:start + 50]
        req = urllib.request.Request(f"{args.studio.rstrip('/')}/api/ingest/products/batch", data=json.dumps(chunk).encode(),
                                     headers={"Content-Type": "application/json", "X-API-Key": args.key}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                res = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            sys.exit(f"HTTP {exc.code}: {exc.read().decode()[:2000]}")
        print(f"rows {start + 1}-{start + len(chunk)}: {res['ok']} ok, {res['failed']} failed")
        for r in res["results"]:
            if not r["ok"]:
                print(f"  {chunk[r['index']]['external_ref']}: {r['error']}")


if __name__ == "__main__":
    main()
