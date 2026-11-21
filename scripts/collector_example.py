#!/usr/bin/env python3
"""Push products from your data-collection software into the studio (ingest API).

    python scripts/collector_example.py --studio http://localhost:8000 --key nqk_... scripts/sample_product.json

The key needs the 'ingest' scope (Settings → API keys). Standard library only.
Re-sending the same product is safe: it is matched on (retailer slug, external_ref),
every send adds a dated price observation, and dimensions create a new revision only
when they change. Records arrive as drafts until a curator reviews them.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def post(studio: str, key: str, path: str, payload) -> dict:
    req = urllib.request.Request(f"{studio.rstrip('/')}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "X-API-Key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code}: {exc.read().decode()[:2000]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--studio", default="http://localhost:8000")
    ap.add_argument("--key", required=True, help="API key with the ingest scope")
    ap.add_argument("files", nargs="+", help="JSON files, each one product or a list of products")
    args = ap.parse_args()
    for path in args.files:
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, list):
            res = post(args.studio, args.key, "/api/ingest/products/batch", data)
            print(f"{path}: {res['ok']} ok, {res['failed']} failed")
            for r in res["results"]:
                if not r["ok"]:
                    print(f"  item {r['index']}: {r['error']}")
        else:
            res = post(args.studio, args.key, "/api/ingest/products", data)
            print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
