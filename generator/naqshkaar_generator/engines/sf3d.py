"""Stable Fast 3D (Stability-AI/stable-fast-3d). Stability AI Community License; gated model.

Setup (see generator/envs/sf3d.sh):
    pip install -e <stable-fast-3d repo>  (or SF3D_REPO=/path/to/stable-fast-3d)
    huggingface-cli login   # after accepting the model terms on huggingface.co/stabilityai/stable-fast-3d
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import Engine, EngineResult, EngineUnavailable, JobContext, add_to_path, require_module, torch_device


class SF3DEngine(Engine):
    code = "sf3d"

    def __init__(self):
        super().__init__()
        self.model = None
        self.session = None
        self.device = None

    def _path(self):
        if os.environ.get("SF3D_REPO"):
            add_to_path(Path(os.environ["SF3D_REPO"]).expanduser().resolve())

    def available(self):
        self._path()
        try:
            require_module("sf3d", "Clone https://github.com/Stability-AI/stable-fast-3d and install it.")
            require_module("rembg", "pip install rembg onnxruntime-gpu")
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def load(self):
        self._path()
        import rembg
        from sf3d.system import SF3D

        self.device = torch_device()
        self.model = SF3D.from_pretrained("stabilityai/stable-fast-3d", config_name="config.yaml",
                                          weight_name="model.safetensors").to(self.device).eval()
        self.session = rembg.new_session()
        self.loaded = True

    def unload(self):
        self.model = None
        self.session = None
        super().unload()

    def generate(self, ctx: JobContext) -> EngineResult:
        import torch
        from PIL import Image
        from sf3d.utils import remove_background, resize_foreground

        ctx.step(10, "sf3d: preparing image")
        img = remove_background(Image.open(ctx.inputs[0].path).convert("RGBA"), self.session)
        img = resize_foreground(img, float(ctx.param("foreground_ratio", 0.85)))
        ctx.step(30, "sf3d: reconstructing")
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            mesh, _ = self.model.run_image([img], bake_resolution=int(ctx.param("texture_resolution", 1024)),
                                           remesh=ctx.param("remesh", "none"),
                                           vertex_count=int(ctx.param("vertex_count", -1)))
        mesh = mesh[0] if isinstance(mesh, (list, tuple)) else mesh
        out = ctx.work_dir / "sf3d.glb"
        mesh.export(str(out), include_normals=True)
        ctx.step(95, "sf3d: done")
        return EngineResult(out, {"engine_version": "stabilityai/stable-fast-3d"})
