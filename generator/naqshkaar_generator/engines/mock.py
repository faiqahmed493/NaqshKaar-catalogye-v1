"""Mock engine: a box with the product photo on its front face. CPU only.

Use it to test the whole studio pipeline (queue → worker → qualification →
review) on any laptop before setting up a GPU engine.
"""
from __future__ import annotations

import time

import numpy as np

from .base import Engine, EngineResult, JobContext


class MockEngine(Engine):
    code = "mock"
    needs_gpu = False

    def available(self):
        try:
            import trimesh  # noqa: F401
        except ImportError:
            return False, "pip install trimesh pillow"
        return True, "ok"

    def generate(self, ctx: JobContext) -> EngineResult:
        import trimesh
        from PIL import Image

        ctx.step(10, "mock: reading image")
        img = Image.open(ctx.inputs[0].path).convert("RGB")
        dims = ctx.target_dimensions_m or {}
        w = dims.get("width") or 1.0
        d = dims.get("depth") or 0.6
        h = dims.get("height") or (w * img.height / img.width)

        delay = float(ctx.param("delay_seconds", 3))
        for n in range(4):
            time.sleep(delay / 4)
            ctx.step(20 + n * 15, f"mock: building ({n + 1}/4)")

        # Body: a box in the photo's average colour.
        body = trimesh.creation.box(extents=[w, h, d])
        body.apply_translation([0, h / 2, 0])
        avg = np.array(img.resize((1, 1)).getpixel((0, 0)) + (255,), dtype=np.uint8)
        body.visual.vertex_colors = np.tile(avg, (len(body.vertices), 1))

        # Front face (+Z): a textured quad slightly in front of the box.
        z = d / 2 + 1e-4
        verts = np.array([[-w / 2, 0, z], [w / 2, 0, z], [w / 2, h, z], [-w / 2, h, z]])
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        front = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        front.visual = trimesh.visual.TextureVisuals(uv=uv, image=img)

        scene = trimesh.Scene([body, front])
        out = ctx.work_dir / "mock.glb"
        out.write_bytes(scene.export(file_type="glb"))
        ctx.step(95, "mock: exported GLB")
        return EngineResult(out, {"engine_version": "mock-1"})
