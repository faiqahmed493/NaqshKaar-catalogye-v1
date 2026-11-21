"""Tencent Hunyuan3D adapters.

hunyuan3d2    Hunyuan3D-2 / 2mini (hy3dgen package): shape, optional texture paint.
hunyuan3d2mv  Hunyuan3D-2mv: multi-view shape from images tagged front/left/back/right.
hunyuan3d21   Hunyuan3D-2.1 (hy3dshape + hy3dpaint): shape, optional PBR paint.

Licences: Hunyuan3D-2 uses the Tencent Hunyuan Community License; Hunyuan3D-2.1 code
states a NON-COMMERCIAL licence. Fine for the FYP; check before any commercial use.

Setup (see generator/envs/hunyuan3d2.sh and hunyuan3d21.sh):
    pip install -e <Hunyuan3D-2 repo>     (hunyuan3d2 / hunyuan3d2mv; texture needs the compiled rasterizer)
    HUNYUAN21_REPO=/path/to/Hunyuan3D-2.1  (hunyuan3d21)
"""
from __future__ import annotations

from pathlib import Path

from .base import (Engine, EngineResult, EngineUnavailable, JobContext, add_to_path, repo_path, require_module,
                   working_dir)


def _rgba(path: Path, remover):
    from PIL import Image

    from ..meshutil import has_transparency

    img = Image.open(path).convert("RGBA")
    return img if has_transparency(path) else remover(img.convert("RGB"))


def _cleanup(mesh):
    from hy3dgen.shapegen import DegenerateFaceRemover, FaceReducer, FloaterRemover
    mesh = FloaterRemover()(mesh)
    mesh = DegenerateFaceRemover()(mesh)
    return FaceReducer()(mesh)


class Hunyuan3D2Engine(Engine):
    code = "hunyuan3d2"
    multiview = False

    def __init__(self):
        super().__init__()
        self.shape = None
        self.paint = None
        self.remover = None
        self.loaded_model = None

    def available(self):
        try:
            require_module("hy3dgen", "Clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2 and pip install -e .")
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def _ensure(self, model: str, subfolder: str, texture: bool):
        from hy3dgen.rembg import BackgroundRemover
        from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

        if self.shape is None or self.loaded_model != (model, subfolder):
            self.shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(model, subfolder=subfolder, variant="fp16")
            self.loaded_model = (model, subfolder)
        if self.remover is None:
            self.remover = BackgroundRemover()
        if texture and self.paint is None:
            try:
                from hy3dgen.texgen import Hunyuan3DPaintPipeline
            except ImportError as exc:
                raise EngineUnavailable("texture painting needs the compiled custom_rasterizer and "
                                        "differentiable_renderer from the Hunyuan3D-2 repo") from exc
            self.paint = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
        self.loaded = True

    def load(self):
        pass  # model choice depends on job params; loaded lazily in generate()

    def unload(self):
        self.shape = self.paint = self.remover = None
        self.loaded_model = None
        super().unload()

    def _image_arg(self, ctx: JobContext):
        return _rgba(ctx.inputs[0].path, self.remover)

    def generate(self, ctx: JobContext) -> EngineResult:
        import torch

        model = ctx.param("model", "tencent/Hunyuan3D-2")
        subfolder = ctx.param("subfolder", "hunyuan3d-dit-v2-0")
        texture = bool(ctx.param("texture", True)) and not self.multiview
        ctx.step(5, f"hunyuan: loading {model}/{subfolder}")
        self._ensure(model, subfolder, texture)
        image = self._image_arg(ctx)
        ctx.step(20, "hunyuan: generating shape")
        mesh = self.shape(image=image, num_inference_steps=int(ctx.param("steps", 50)),
                          octree_resolution=int(ctx.param("octree_resolution", 380)), num_chunks=20000,
                          generator=torch.manual_seed(int(ctx.param("seed", 1234))), output_type="trimesh")[0]
        mesh = _cleanup(mesh)
        if texture:
            ctx.step(55, "hunyuan: painting texture")
            ref = image if not isinstance(image, dict) else image["front"]
            mesh = self.paint(mesh, image=ref)
        out = ctx.work_dir / f"{self.code}.glb"
        mesh.export(str(out))
        ctx.step(95, "hunyuan: done")
        return EngineResult(out, {"engine_version": f"{model}/{subfolder}", "textured": texture})


class Hunyuan3D2MVEngine(Hunyuan3D2Engine):
    code = "hunyuan3d2mv"
    multiview = True

    def _image_arg(self, ctx: JobContext):
        views = {}
        for i in ctx.inputs:
            if i.view_angle in ("front", "left", "back", "right") and i.view_angle not in views:
                views[i.view_angle] = _rgba(i.path, self.remover)
        if "front" not in views:
            raise ValueError("hunyuan3d2mv needs an image tagged 'front'")
        return views

    def generate(self, ctx: JobContext) -> EngineResult:
        ctx.params.setdefault("model", "tencent/Hunyuan3D-2mv")
        ctx.params.setdefault("subfolder", "hunyuan3d-dit-v2-mv")
        return super().generate(ctx)


class Hunyuan3D21Engine(Engine):
    code = "hunyuan3d21"

    def __init__(self):
        super().__init__()
        self.repo: Path | None = None
        self.shape = None
        self.paint = None
        self.remover = None

    def available(self):
        try:
            repo_path("HUNYUAN21_REPO", "Clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 and follow its install steps.")
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def load(self):
        self.repo = repo_path("HUNYUAN21_REPO", "")
        add_to_path(self.repo / "hy3dshape", self.repo / "hy3dpaint")
        with working_dir(self.repo):
            from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
            from hy3dshape.rembg import BackgroundRemover
            self.shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2.1")
            self.remover = BackgroundRemover()
        self.loaded = True

    def unload(self):
        self.shape = self.paint = self.remover = None
        super().unload()

    def generate(self, ctx: JobContext) -> EngineResult:
        from ..meshutil import to_glb

        texture = bool(ctx.param("texture", True))
        with working_dir(self.repo):
            image = _rgba(ctx.inputs[0].path, self.remover)
            ctx.step(15, "hunyuan3d21: generating shape")
            mesh = self.shape(image=image)[0]
            shape_path = ctx.work_dir / "shape.glb"
            mesh.export(str(shape_path))
            if not texture:
                ctx.step(95, "hunyuan3d21: done (shape only)")
                return EngineResult(shape_path, {"engine_version": "Hunyuan3D-2.1", "textured": False})
            ctx.step(50, "hunyuan3d21: painting PBR textures")
            if self.paint is None:
                try:
                    from utils.torchvision_fix import apply_fix
                    apply_fix()
                except Exception:  # noqa: BLE001 - optional compatibility shim from the repo
                    pass
                from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline
                conf = Hunyuan3DPaintConfig(int(ctx.param("max_num_view", 6)), int(ctx.param("paint_resolution", 512)))
                self.paint = Hunyuan3DPaintPipeline(conf)
            ref_path = ctx.work_dir / "reference.png"
            image.save(ref_path)
            painted = self.paint(mesh_path=str(shape_path), image_path=str(ref_path))
        out = to_glb(Path(painted), ctx.work_dir / "hunyuan3d21.glb")
        ctx.step(95, "hunyuan3d21: done")
        return EngineResult(out, {"engine_version": "Hunyuan3D-2.1", "textured": True})
