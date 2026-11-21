"""TRELLIS (microsoft/TRELLIS, MIT). Single- or multi-image conditioning.

Setup (see generator/envs/trellis.sh):
    TRELLIS_REPO=/path/to/TRELLIS     # repository root (contains the 'trellis' package)
    TRELLIS_MODEL=microsoft/TRELLIS-image-large   (default)
    ATTN_BACKEND=xformers             # optional; 'flash-attn' is the repo default
"""
from __future__ import annotations

import os

from .base import Engine, EngineResult, EngineUnavailable, JobContext, add_to_path, repo_path, seed_everything


class TrellisEngine(Engine):
    code = "trellis"

    def __init__(self):
        super().__init__()
        self.pipe = None

    def available(self):
        try:
            add_to_path(repo_path("TRELLIS_REPO", "Clone https://github.com/microsoft/TRELLIS and run its setup.sh."))
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def load(self):
        os.environ.setdefault("SPCONV_ALGO", "native")
        add_to_path(repo_path("TRELLIS_REPO", ""))
        from trellis.pipelines import TrellisImageTo3DPipeline

        self.pipe = TrellisImageTo3DPipeline.from_pretrained(os.environ.get("TRELLIS_MODEL", "microsoft/TRELLIS-image-large"))
        self.pipe.cuda()
        self.loaded = True

    def unload(self):
        self.pipe = None
        super().unload()

    def generate(self, ctx: JobContext) -> EngineResult:
        from PIL import Image
        from trellis.utils import postprocessing_utils

        seed = int(ctx.param("seed", 1))
        seed_everything(seed)
        ss = {"steps": int(ctx.param("ss_steps", 12)), "cfg_strength": float(ctx.param("ss_cfg", 7.5))}
        slat = {"steps": int(ctx.param("slat_steps", 12)), "cfg_strength": float(ctx.param("slat_cfg", 3.0))}
        images = [Image.open(i.path) for i in ctx.inputs]
        ctx.step(15, f"trellis: generating from {len(images)} image(s)")
        if len(images) > 1:
            outputs = self.pipe.run_multi_image(images, seed=seed, sparse_structure_sampler_params=ss,
                                                slat_sampler_params=slat,
                                                mode=ctx.param("multi_image_mode", "stochastic"))
        else:
            outputs = self.pipe.run(images[0], seed=seed, sparse_structure_sampler_params=ss, slat_sampler_params=slat)
        ctx.step(70, "trellis: baking texture and exporting GLB")
        glb = postprocessing_utils.to_glb(outputs["gaussian"][0], outputs["mesh"][0],
                                          simplify=float(ctx.param("simplify", 0.95)),
                                          texture_size=int(ctx.param("texture_size", 1024)))
        out = ctx.work_dir / "trellis.glb"
        glb.export(str(out))
        ctx.step(95, "trellis: done")
        return EngineResult(out, {"engine_version": "TRELLIS-image-large", "seed": seed, "images": len(images)})
