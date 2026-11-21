"""End-to-end self-test. Runs the whole catalogue flow against the live API:

  sign in → create a product with dimensions and price → upload an image → check the link
  → generate a 3D model with the mock engine → automated checks → approve and publish
  → read it back from the planner's catalogue API → download the GLB → clean up

Inside Docker (uses the bootstrap admin from .env):
    docker compose exec api python -m app.smoke
Options:
    --keep            leave the test product in the catalogue
    --engine trellis  test a real GPU engine instead of the mock one
    --timeout 900     seconds to wait for generation (real engines are slower)
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
from datetime import datetime, timezone

import httpx

OK, BAD, INFO = "[ OK ]", "[FAIL]", "[ .. ]"


class SmokeFailure(RuntimeError):
    pass


def png_bytes() -> bytes:
    """A simple chair silhouette on white, so engines have something to reconstruct."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (512, 512), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([150, 90, 360, 260], fill=(90, 110, 130))      # back rest
    d.rectangle([140, 260, 370, 310], fill=(70, 90, 110))      # seat
    for x in (150, 340):
        d.rectangle([x, 310, x + 20, 460], fill=(60, 45, 35))  # legs
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Smoke:
    def __init__(self, base: str, email: str, password: str, engine: str, timeout: int):
        self.base = base.rstrip("/")
        self.http = httpx.Client(base_url=self.base, timeout=60)
        self.email, self.password, self.engine, self.timeout = email, password, engine, timeout
        self.product_id: str | None = None
        self.variant_id: str | None = None

    # ------------------------------------------------------------------ helpers
    def call(self, method: str, path: str, expect: tuple[int, ...] = (200, 201), **kw):
        r = self.http.request(method, path, **kw)
        if r.status_code not in expect:
            raise SmokeFailure(f"{method} {path} -> HTTP {r.status_code}: {r.text[:800]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r

    @staticmethod
    def step(msg: str) -> None:
        print(f"{OK} {msg}", flush=True)

    # ------------------------------------------------------------------ flow
    def run(self, keep: bool) -> None:
        self.call("GET", "/api/health")
        self.step(f"API is up at {self.base}")

        tok = self.call("POST", "/api/auth/login", json={"email": self.email, "password": self.password})
        self.http.headers["Authorization"] = f"Bearer {tok['access_token']}"
        self.step(f"signed in as {tok['user']['email']} ({tok['user']['role']})")

        eng = self.call("GET", "/api/engines")
        engine = next((e for e in eng["engines"] if e["code"] == self.engine), None)
        if engine is None:
            raise SmokeFailure(f"engine '{self.engine}' is not in the registry")
        if not engine["online_workers"]:
            raise SmokeFailure(
                f"no worker is online for '{self.engine}'. Start one first "
                f"(for the mock engine: docker compose --profile mock up -d generator-mock), then rerun.")
        self.step(f"{engine['online_workers']} worker(s) online for '{self.engine}'")

        cats = self.call("GET", "/api/categories")
        chair = next(c for c in cats if c["code"] == "study_chair")
        retailers = self.call("GET", "/api/retailers")
        retailer = next((r for r in retailers if r["slug"] == "smoke-test"), None) or self.call(
            "POST", "/api/retailers", json={"name": "Smoke Test Retailer", "slug": "smoke-test",
                                            "website_url": "https://example.com", "city": "Karachi"})
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        url = f"https://example.com/smoke-test/{stamp}"
        created = self.call("POST", "/api/products", json={
            "retailer_id": retailer["id"], "name": f"Smoke Test Chair {stamp}", "category_id": chair["id"],
            "listing_url": url,
            "variant": {
                "variant_key": "SMOKE-1", "variant_label": "grey", "sale_unit": "single", "sale_unit_quantity": 1,
                "dimensions": {"kind": "assembled", "width": {"value": "55", "unit": "cm"},
                               "depth": {"value": "58", "unit": "cm"}, "height": {"value": "92", "unit": "cm"},
                               "source_text": "W55 x D58 x H92 cm", "source_ref": url},
                "price": {"price_pkr": "24500", "availability": "in_stock", "source_url": url,
                          "checked_at": datetime.now(timezone.utc).isoformat()},
                "room_uses": [{"room_type": "study", "use_tag": "study_chair"}],
                "attributes": [{"key": "colour", "value": "grey", "source": "curator", "verified": True}],
            },
        })
        self.product_id, self.variant_id = created["product"]["id"], created["variant_id"]
        self.step("created product, variant, dimension revision (55 × 58 × 92 cm) and dated price")

        up = self.call("POST", f"/api/products/{self.product_id}/images",
                       data={"variant_id": self.variant_id, "view_angle": "front", "role": "primary",
                             "depicts_variant": "true"},
                       files=[("files", ("smoke-chair.png", png_bytes(), "image/png"))])
        image_id = (up["created"] or up["duplicates"])[0]["id"]
        self.step("uploaded and processed an image (original, PNG for engines, thumbnail)")

        self.call("POST", f"/api/variants/{self.variant_id}/link-checks", json={"outcome": "ok"})
        adm = self.call("GET", f"/api/variants/{self.variant_id}/admission")
        if not adm["all_required_pass"]:
            failed = [f"{c['label']}: {c['detail']}" for c in adm["conditions"] if c["required"] and not c["passed"]]
            raise SmokeFailure("admission conditions should all pass but these fail: " + "; ".join(failed))
        self.step(f"all {sum(c['required'] for c in adm['conditions'])} required admission conditions pass")

        jobs = self.call("POST", f"/api/variants/{self.variant_id}/generation-jobs",
                         json={"engine_codes": [self.engine], "image_ids": [image_id]})
        job_id = jobs[0]["id"]
        print(f"{INFO} queued {self.engine} job {job_id[:8]}; waiting for a worker (timeout {self.timeout}s)", flush=True)
        job = self.wait_job(job_id)
        meta = job.get("runtime_meta") or {}
        self.step(f"job finished on {job['worker_id']} in {meta.get('seconds', '?')} s")

        asset = self.wait_asset(job["result_asset_id"])
        for c in asset["checks"]:
            mark = {"pass": OK, "fail": BAD, "warn": "[WARN]", "not_run": INFO}[c["outcome"]]
            print(f"       {mark} {c['code']}: {c['message'] or ''}")
        if asset["status"] != "in_review":
            raise SmokeFailure(f"asset ended as '{asset['status']}': {asset.get('processing_error')}")
        ext = asset["scaled_extents_m"]
        self.step(f"automated checks pass; scaled to {ext['width']:.3f} × {ext['depth']:.3f} × {ext['height']:.3f} m")

        checklist = {k: True for k in ("correct_item", "silhouette", "components", "no_staging_objects",
                                       "no_missing_parts", "no_scale_distortion")}
        pub = self.call("POST", f"/api/variants/{self.variant_id}/publish",
                        json={"asset_id": asset["id"], "checklist": checklist, "comment": "smoke test"})
        if pub["status"] != "eligible" or not pub["asset_ready"]:
            raise SmokeFailure(f"publish left status={pub['status']} asset_ready={pub['asset_ready']}")
        self.step("asset approved, variant admitted to the catalogue")

        cat = self.call("GET", "/api/catalogue/variants", params={"asset_ready": "true", "room_type": "study"})
        item = next((i for i in cat["items"] if i["variant_id"] == self.variant_id), None)
        if not item or not item["glb_url"]:
            raise SmokeFailure("variant is missing from the planner catalogue API")
        glb = self.http.get(item["glb_url"])
        if glb.status_code != 200 or glb.content[:4] != b"glTF":
            raise SmokeFailure(f"GLB download failed (HTTP {glb.status_code})")
        self.step(f"planner API returns it with price PKR {item['price_pkr']} and a {len(glb.content):,}-byte GLB")

        if keep:
            print(f"{INFO} kept: open /variants/{self.variant_id} in the web UI to see it")
        else:
            self.cleanup()

    def wait_job(self, job_id: str) -> dict:
        deadline = time.time() + self.timeout
        last = None
        while time.time() < deadline:
            job = self.call("GET", f"/api/jobs/{job_id}")
            if job["status"] != last:
                print(f"{INFO} job status: {job['status']}", flush=True)
                last = job["status"]
            if job["status"] in ("succeeded",) or (job["status"] in ("uploaded", "postprocessing") and job["result_asset_id"]):
                return job
            if job["status"] in ("failed", "cancelled"):
                raise SmokeFailure(f"job {job['status']}: {job['error_message']}\n--- log ---\n{job.get('log', '')[-2000:]}")
            time.sleep(3)
        raise SmokeFailure(f"job still '{last}' after {self.timeout}s. Is the worker running? "
                           "Check: docker compose logs generator-mock")

    def wait_asset(self, asset_id: str) -> dict:
        deadline = time.time() + 300
        while time.time() < deadline:
            a = self.call("GET", f"/api/assets/{asset_id}")
            if a["status"] != "processing":
                return a
            time.sleep(3)
        raise SmokeFailure("asset still 'processing' after 300 s. Is the CPU worker running? "
                           "Check: docker compose logs worker")

    def cleanup(self) -> None:
        if not self.product_id:
            return
        try:
            if self.variant_id:
                self.call("POST", f"/api/variants/{self.variant_id}/retire", json={"reason": "smoke test"})
            self.call("DELETE", f"/api/products/{self.product_id}")
            self.step("removed the test product (use --keep to leave it)")
        except SmokeFailure as exc:
            print(f"{INFO} cleanup skipped: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("SMOKE_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--email", default=os.environ.get("BOOTSTRAP_ADMIN_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("BOOTSTRAP_ADMIN_PASSWORD"))
    ap.add_argument("--engine", default="mock")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if not args.email or not args.password:
        sys.exit("Give --email and --password (or set BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD).")
    s = Smoke(args.base, args.email, args.password, args.engine, args.timeout)
    try:
        s.run(args.keep)
    except SmokeFailure as exc:
        print(f"{BAD} {exc}", flush=True)
        if not args.keep:
            s.cleanup()
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"{BAD} cannot reach the API at {args.base}: {exc}")
        sys.exit(1)
    print("\nSelf-test passed: the studio works end to end.")


if __name__ == "__main__":
    main()
