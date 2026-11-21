"""TripoSR (VAST-AI-Research/TripoSR, MIT). Fast single-image reconstruction, ~6 GB VRAM.

Setup (see generator/envs/triposr.sh):
    TRIPOSR_REPO=/path/to/TripoSR    # contains the 'tsr' package
"""
from __future__ import annotations

from .base import (Engine, EngineResult, EngineUnavailable, JobContext, add_to_path, repo_path, require_module,
                   torch_device)


class TripoSREngine(Engine):
    code = "triposr"

    def __init__(self):
        super().__init__()
        self.model = None
        self.session = None
        self.device = None

    def available(self):
        try:
            add_to_path(repo_path("TRIPOSR_REPO", "Clone https://github.com/VAST-AI-Research/TripoSR and pip install -r requirements.txt."))
            require_module("rembg", "pip install rembg onnxruntime-gpu")
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def load(self):
        add_to_path(repo_path("TRIPOSR_REPO", ""))
        import rembg
        from tsr.system import TSR

        self.device = torch_device()
        self.model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
        self.model.renderer.set_chunk_size(8192)
        self.model.to(self.device)
        self.session = rembg.new_session()
        self.loaded = True

    def unload(self):
        self.model = None
        self.session = None
        super().unload()

    def generate(self, ctx: JobContext) -> EngineResult:
        import numpy as np
        import torch
        from PIL import Image
        from tsr.utils import remove_background, resize_foreground

        from ..meshutil import has_transparency, to_glb

        self.model.renderer.set_chunk_size(int(ctx.param("chunk_size", 8192)))
        path = ctx.inputs[0].path
        ctx.step(10, "triposr: preparing image")
        image = Image.open(path)
        if not has_transparency(path):
            image = remove_background(image, self.session)
        image = resize_foreground(image.convert("RGBA"), float(ctx.param("foreground_ratio", 0.85)))
        arr = np.array(image).astype(np.float32) / 255.0
        arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5   # grey background, as in run.py
        image = Image.fromarray((arr * 255.0).astype(np.uint8))

        ctx.step(30, "triposr: reconstructing")
        with torch.no_grad():
            scene_codes = self.model([image], device=self.device)
        ctx.step(60, "triposr: extracting mesh")
        meshes = self.model.extract_mesh(scene_codes, True, resolution=int(ctx.param("mc_resolution", 256)))
        out = ctx.work_dir / "triposr.glb"
        # TripoSR is Z-up; the same turn its Gradio demo applies gives glTF's Y-up.
        to_glb(meshes[0], out, rotate_deg=(-90, 90, 0))
        ctx.step(95, "triposr: done")
        return EngineResult(out, {"engine_version": "stabilityai/TripoSR"})
