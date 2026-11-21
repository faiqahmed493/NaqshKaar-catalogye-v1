"""Meshy (commercial API, not open source). Optional; needs MESHY_API_KEY.

Uses POST /openapi/v1/image-to-3d for one image and /openapi/v1/multi-image-to-3d for
2–4 images, polls the task, then downloads model_urls.glb. Images are sent as
base64 data URIs, so the studio does not need to be publicly reachable. Product
photos leave your infrastructure when you use this engine.
"""
from __future__ import annotations

import base64
import os
import time

import httpx

from .base import Engine, EngineResult, EngineUnavailable, JobContext

API = os.environ.get("MESHY_API_BASE", "https://api.meshy.ai")


class MeshyEngine(Engine):
    code = "meshy"
    needs_gpu = False

    def available(self):
        if not os.environ.get("MESHY_API_KEY"):
            return False, "MESHY_API_KEY is not set"
        return True, "ok"

    def generate(self, ctx: JobContext) -> EngineResult:
        key = os.environ.get("MESHY_API_KEY")
        if not key:
            raise EngineUnavailable("MESHY_API_KEY is not set")
        uris = []
        for i in ctx.inputs[:4]:
            mime = "image/png" if i.path.suffix.lower() == ".png" else "image/jpeg"
            uris.append(f"data:{mime};base64,{base64.b64encode(i.path.read_bytes()).decode()}")
        body = {"ai_model": ctx.param("ai_model", "latest"), "should_texture": bool(ctx.param("should_texture", True)),
                "target_polycount": int(ctx.param("target_polycount", 30000)), "target_formats": ["glb"]}
        if len(uris) == 1:
            path, body["image_url"] = "/openapi/v1/image-to-3d", uris[0]
        else:
            path, body["image_urls"] = "/openapi/v1/multi-image-to-3d", uris
        headers = {"Authorization": f"Bearer {key}"}
        with httpx.Client(base_url=API, headers=headers, timeout=60) as http:
            ctx.step(5, f"meshy: creating task ({len(uris)} image(s))")
            r = http.post(path, json=body)
            r.raise_for_status()
            task_id = r.json()["result"]
            deadline = time.time() + int(ctx.param("timeout_seconds", 1800))
            while True:
                if time.time() > deadline:
                    raise TimeoutError("meshy task timed out")
                t = http.get(f"{path}/{task_id}").json()
                status = t.get("status")
                ctx.step(5 + 0.85 * float(t.get("progress") or 0), f"meshy: {status}")
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "CANCELED"):
                    raise RuntimeError(f"meshy task {status}: {(t.get('task_error') or {}).get('message')}")
                time.sleep(8)
            glb_url = (t.get("model_urls") or {}).get("glb")
            if not glb_url:
                raise RuntimeError("meshy returned no GLB")
            out = ctx.work_dir / "meshy.glb"
            with httpx.stream("GET", glb_url, timeout=300, follow_redirects=True) as d:
                d.raise_for_status()
                with out.open("wb") as fh:
                    for chunk in d.iter_bytes():
                        fh.write(chunk)
        ctx.step(95, "meshy: downloaded")
        return EngineResult(out, {"engine_version": f"meshy:{body['ai_model']}", "task_id": task_id,
                                  "consumed_credits": t.get("consumed_credits")})
