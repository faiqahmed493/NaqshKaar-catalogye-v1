"""TRELLIS through a Hugging Face Space (microsoft/TRELLIS, MIT). No local GPU needed.

Calls the public Gradio Space (default trellis-community/TRELLIS) with gradio_client:
/start_session → /preprocess_image → /generate_and_extract_glb. Product photos are
uploaded to Hugging Face. Free use is limited by the Space's ZeroGPU quota; a free
Hugging Face access token raises it.

    TRELLIS_HF_SPACE=trellis-community/TRELLIS   (default)
    HF_TOKEN=hf_...                              optional, read scope is enough
"""
from __future__ import annotations

import os
import shutil
import time

from .base import Engine, EngineResult, JobContext

DEFAULT_SPACE = "trellis-community/TRELLIS"


class TrellisHFEngine(Engine):
    code = "trellis_hf"
    needs_gpu = False

    def available(self):
        try:
            import gradio_client  # noqa: F401
        except ImportError:
            return False, "pip install gradio_client"
        return True, "ok"

    def generate(self, ctx: JobContext) -> EngineResult:
        from gradio_client import Client, handle_file

        space = ctx.param("space") or os.environ.get("TRELLIS_HF_SPACE") or DEFAULT_SPACE
        ctx.step(5, f"trellis_hf: connecting to {space}")
        client = Client(space, token=os.environ.get("HF_TOKEN") or None, verbose=False)
        client.predict(api_name="/start_session")

        ctx.step(10, "trellis_hf: removing background")
        image = self._wait(ctx, client.submit(handle_file(str(ctx.inputs[0].path)), api_name="/preprocess_image"),
                           "preprocessing", 15)

        seed = int(ctx.param("seed", 1))
        ctx.step(20, "trellis_hf: generating")
        out = self._wait(ctx, client.submit(
            handle_file(image), [], seed,
            float(ctx.param("ss_cfg", 7.5)), int(ctx.param("ss_steps", 12)),
            float(ctx.param("slat_cfg", 3.0)), int(ctx.param("slat_steps", 12)),
            "stochastic", float(ctx.param("simplify", 0.95)), int(ctx.param("texture_size", 1024)),
            api_name="/generate_and_extract_glb"), "generating", 25)

        glb = out[2]                                   # (preview video, model viewer, download_glb)
        if isinstance(glb, dict):
            glb = glb.get("value") or glb.get("path")
        if not glb or not os.path.exists(glb):
            raise RuntimeError(f"{space} returned no GLB")
        dest = ctx.work_dir / "trellis_hf.glb"
        shutil.copyfile(glb, dest)
        ctx.step(95, "trellis_hf: downloaded GLB")
        return EngineResult(dest, {"engine_version": f"TRELLIS-image-large via {space}", "seed": seed, "images": 1})

    def _wait(self, ctx: JobContext, job, stage: str, progress: float):
        """Poll a Gradio job so the studio sees queue position and can cancel it."""
        deadline = time.time() + int(ctx.param("timeout_seconds", 900))
        last = None
        try:
            while not job.done():
                if time.time() > deadline:
                    raise TimeoutError(f"trellis_hf: {stage} timed out")
                st = job.status()
                msg = f"trellis_hf: {stage} ({st.code.name.lower()}"
                msg += f", queue position {st.rank + 1})" if st.rank is not None and st.rank >= 0 else ")"
                if msg != last:
                    ctx.step(progress, msg)
                    last = msg
                else:
                    ctx.step(progress, None)       # still raises if the job was cancelled
                time.sleep(2)
            return job.result()
        except Exception as exc:
            job.cancel()
            if "quota" in str(exc).lower():
                raise RuntimeError(f"Hugging Face GPU quota reached ({exc}). Wait for it to reset, or set HF_TOKEN "
                                   "on the worker to use your account's quota.") from exc
            raise
