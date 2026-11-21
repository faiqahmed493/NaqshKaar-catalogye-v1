"""Engines that run an external command: InstantMesh and a generic template for any model.

instantmesh
    INSTANTMESH_REPO=/path/to/InstantMesh
    INSTANTMESH_PYTHON=/path/to/conda/envs/instantmesh/bin/python   (default: python)

command  (plug in any open-source image-to-3D model that has a CLI)
    GENERATOR_COMMAND_TEMPLATE='python /opt/mymodel/run.py --image {input} --out {output_dir}'
    GENERATOR_COMMAND_CWD=/opt/mymodel           (optional)
    GENERATOR_COMMAND_ROTATE=-90,0,0             (optional: degrees X,Y,Z to make the result Y-up)
  Placeholders: {input} first image, {inputs} all images (space separated), {output_dir},
  {output} suggested output path (.glb), {params_json} job params as JSON.
  The newest .glb/.gltf/.obj/.ply/.stl written under {output_dir} is taken as the result.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from .base import Engine, EngineResult, EngineUnavailable, JobCancelled, JobContext, repo_path

MESH_SUFFIXES = (".glb", ".gltf", ".obj", ".ply", ".stl")


def _run(cmd: list[str], cwd: Path | None, ctx: JobContext, timeout_s: int, log_name: str) -> None:
    log_path = ctx.work_dir / f"{log_name}.log"
    with log_path.open("w") as log:
        proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=log, stderr=subprocess.STDOUT)
        started = time.time()
        while proc.poll() is None:
            if ctx.cancel_event.is_set():
                proc.kill()
                raise JobCancelled("cancelled from the studio")
            if time.time() - started > timeout_s:
                proc.kill()
                raise TimeoutError(f"{log_name} exceeded {timeout_s}s")
            time.sleep(2)
    if proc.returncode != 0:
        tail = log_path.read_text()[-3000:]
        raise RuntimeError(f"{log_name} exited with code {proc.returncode}:\n{tail}")


def _newest_mesh(root: Path) -> Path:
    found = [p for p in root.rglob("*") if p.suffix.lower() in MESH_SUFFIXES]
    if not found:
        raise RuntimeError(f"no mesh file was written under {root}")
    return max(found, key=lambda p: p.stat().st_mtime)


class InstantMeshEngine(Engine):
    code = "instantmesh"

    def available(self):
        try:
            repo_path("INSTANTMESH_REPO", "Clone https://github.com/TencentARC/InstantMesh and install its requirements.")
        except EngineUnavailable as exc:
            return False, str(exc)
        return True, "ok"

    def generate(self, ctx: JobContext) -> EngineResult:
        from ..meshutil import to_glb

        repo = repo_path("INSTANTMESH_REPO", "")
        python = os.environ.get("INSTANTMESH_PYTHON", "python")
        out_dir = ctx.work_dir / "instantmesh_out"
        cmd = [python, "run.py", str(ctx.param("config", "configs/instant-mesh-large.yaml")), str(ctx.inputs[0].path),
               "--output_path", str(out_dir), "--seed", str(int(ctx.param("seed", 42)))]
        if ctx.param("export_texmap", True):
            cmd.append("--export_texmap")
        ctx.step(10, "instantmesh: running (multi-view diffusion, then reconstruction)")
        _run(cmd, repo, ctx, int(ctx.param("timeout_seconds", 1800)), "instantmesh")
        mesh = _newest_mesh(out_dir)
        out = to_glb(mesh, ctx.work_dir / "instantmesh.glb")
        ctx.step(95, "instantmesh: done")
        return EngineResult(out, {"engine_version": "TencentARC/InstantMesh", "source_file": mesh.name})


class CommandEngine(Engine):
    code = "command"
    needs_gpu = False

    def available(self):
        if not os.environ.get("GENERATOR_COMMAND_TEMPLATE"):
            return False, "GENERATOR_COMMAND_TEMPLATE is not set"
        return True, "ok"

    def generate(self, ctx: JobContext) -> EngineResult:
        from ..meshutil import to_glb

        template = os.environ["GENERATOR_COMMAND_TEMPLATE"]
        out_dir = ctx.work_dir / "command_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        params_file = ctx.work_dir / "params.json"
        params_file.write_text(json.dumps(ctx.params))
        values = {
            "input": shlex.quote(str(ctx.inputs[0].path)),
            "inputs": " ".join(shlex.quote(str(i.path)) for i in ctx.inputs),
            "output_dir": shlex.quote(str(out_dir)),
            "output": shlex.quote(str(out_dir / "result.glb")),
            "params_json": shlex.quote(str(params_file)),
        }
        cmd = shlex.split(template.format(**values))
        cwd = Path(os.environ["GENERATOR_COMMAND_CWD"]) if os.environ.get("GENERATOR_COMMAND_CWD") else None
        ctx.step(10, f"command: {cmd[0]} …")
        _run(cmd, cwd, ctx, int(ctx.param("timeout_seconds", 3600)), "command")
        rot = tuple(float(x) for x in os.environ.get("GENERATOR_COMMAND_ROTATE", "0,0,0").split(","))
        mesh = _newest_mesh(out_dir)
        out = to_glb(mesh, ctx.work_dir / "command.glb", rotate_deg=rot)  # type: ignore[arg-type]
        ctx.step(95, "command: done")
        return EngineResult(out, {"engine_version": "custom-command", "command": cmd[0]})
