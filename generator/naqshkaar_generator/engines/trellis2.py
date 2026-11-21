"""TRELLIS.2 (microsoft/TRELLIS.2, MIT). Single image, PBR textures, 24 GB GPU.

Setup (see generator/envs/trellis2.sh):
    TRELLIS2_REPO=/path/to/TRELLIS.2
    TRELLIS2_MODEL=microsoft/TRELLIS.2-4B   (default)
"""
from __future__ import annotations

import os

from .base import Engine, EngineResult, EngineUnavailable, JobContext, add_to_path, repo_path, seed_everything


class Trellis2Engine(Engine):
    code = "trellis2"

    def __init__(self):
        super().__init__()
        self.pipe = None

    def available(self):
        try:
            add_to_path(repo_path("TRELLIS2_REPO", "Clone https://github.com/microsoft/TRELLIS.2 and run setup.sh."))
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def load(self):
        add_to_path(repo_path("TRELLIS2_REPO", ""))
        from trellis2.pipelines import Trellis2ImageTo3DPipeline

        self.pipe = Trellis2ImageTo3DPipeline.from_pretrained(os.environ.get("TRELLIS2_MODEL", "microsoft/TRELLIS.2-4B"))
        self.pipe.cuda()
        self.loaded = True

    def unload(self):
        self.pipe = None
        super().unload()

    def generate(self, ctx: JobContext) -> EngineResult:
        import o_voxel
        from PIL import Image

        seed = int(ctx.param("seed", 1))
        seed_everything(seed)
        image = Image.open(ctx.inputs[0].path)
        ctx.step(15, "trellis2: generating")
        kwargs = {"seed": seed}
        if ctx.param("pipeline_type"):
            kwargs["pipeline_type"] = ctx.param("pipeline_type")
        try:
            mesh = self.pipe.run(image, **kwargs)[0]
        except TypeError:  # older checkouts without these keyword arguments
            mesh = self.pipe.run(image)[0]
        mesh.simplify(16777216)  # nvdiffrast limit, as in the official example
        ctx.step(65, "trellis2: remeshing, baking PBR textures")
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs, coords=mesh.coords,
            attr_layout=mesh.layout, voxel_size=mesh.voxel_size, aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=int(ctx.param("decimation_target", 500000)),
            texture_size=int(ctx.param("texture_size", 2048)), remesh=True, remesh_band=1, remesh_project=0,
            verbose=False,
        )
        out = ctx.work_dir / "trellis2.glb"
        # PNG textures (not WebP) so the studio's checker and any glTF viewer can open the file.
        glb.export(str(out), extension_webp=False)
        ctx.step(95, "trellis2: done")
        return EngineResult(out, {"engine_version": "TRELLIS.2-4B", "seed": seed})
