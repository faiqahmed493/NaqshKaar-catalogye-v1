"""Generation worker loop.

    STUDIO_URL=http://localhost:8000 STUDIO_API_KEY=nqk_... ENGINES=trellis python -m naqshkaar_generator

Per job: download inputs (signed URLs) → run the engine → upload one GLB.
A heartbeat thread keeps the job alive while the model runs and passes on
cancellation from the studio. GPU_LOCK_FILE stops two workers on the same
machine from loading models into one GPU at the same time.
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import platform
import shutil
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

import httpx

from . import __version__
from .client import StudioClient
from .config import WorkerConfig
from .engines import REGISTRY
from .engines.base import Engine, EngineUnavailable, InputImage, JobCancelled, JobContext

log = logging.getLogger("naqshkaar.generator")


def gpu_info() -> dict:
    info = {"hostname": platform.node()}
    try:
        import torch
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info.update(gpu_name=p.name, gpu_vram_gb=round(p.total_memory / 1024 ** 3, 1))
    except ImportError:
        pass
    return info


@contextlib.contextmanager
def gpu_lock(path: str | None, needed: bool):
    if not path or not needed:
        yield
        return
    try:
        import fcntl
    except ImportError:  # Windows: no advisory lock, run one GPU worker per machine instead
        yield
        return
    with open(path, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class Worker:
    def __init__(self, cfg: WorkerConfig):
        self.cfg = cfg
        self.client = StudioClient(cfg)
        self.gpu = gpu_info()
        self.engines: dict[str, Engine] = {}
        self.loaded: OrderedDict[str, Engine] = OrderedDict()
        for code in cfg.engines:
            cls = REGISTRY.get(code)
            if cls is None:
                log.error("unknown engine '%s' (known: %s)", code, ", ".join(sorted(REGISTRY)))
                continue
            eng = cls()
            ok, why = eng.available()
            if ok:
                self.engines[code] = eng
                log.info("engine %-12s ready", code)
            else:
                log.warning("engine %-12s unavailable: %s", code, why)
        if not self.engines:
            raise SystemExit("No requested engine is usable on this machine; see the warnings above.")

    @property
    def needs_gpu(self) -> bool:
        return any(e.needs_gpu for e in self.engines.values())

    def _ensure_loaded(self, eng: Engine) -> None:
        if eng.code in self.loaded:
            self.loaded.move_to_end(eng.code)
            return
        while len(self.loaded) >= self.cfg.max_loaded_engines:
            code, old = self.loaded.popitem(last=False)
            log.info("unloading %s to free memory", code)
            old.unload()
        log.info("loading %s (first job may take a while: weights download)", eng.code)
        eng.load()
        self.loaded[eng.code] = eng

    # ------------------------------------------------------------------ job
    def run_job(self, job: dict) -> None:
        job_id, code = job["job_id"], job["engine"]
        eng = self.engines[code]
        work = self.cfg.work_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        cancel = threading.Event()
        last = {"p": 0.0, "msg": None}
        lines: list[str] = []
        stop = threading.Event()

        def report(progress, message):
            if progress is not None:
                last["p"] = progress
            if message:
                log.info("[%s] %s", job_id[:8], message)
                lines.append(message)

        def heartbeat():
            while not stop.wait(self.cfg.heartbeat_seconds):
                try:
                    pending = "\n".join(lines) or None
                    lines.clear()
                    r = self.client.progress(job_id, last["p"], pending)
                    if r.get("cancel"):
                        cancel.set()
                except Exception as exc:  # noqa: BLE001
                    log.warning("heartbeat failed: %s", exc)

        hb = threading.Thread(target=heartbeat, daemon=True)
        started = time.time()
        try:
            self.client.progress(job_id, 1, f"[worker {self.cfg.worker_id}] starting {code}")
            inputs = []
            for item in sorted(job["inputs"], key=lambda i: i["position"]):
                dest = work / f"input_{item['position']:02d}.png"
                self.client.download(item["url"], dest)
                inputs.append(InputImage(dest, item.get("view_angle", "unknown"), item.get("role", "gallery")))
            hb.start()
            ctx = JobContext(job_id=job_id, params=dict(job.get("params") or {}), inputs=inputs, work_dir=work,
                             target_dimensions_m=job.get("target_dimensions_m"), product=job.get("product") or {},
                             report=report, cancel_event=cancel)
            ctx.step(3, f"loading {code}")
            self._ensure_loaded(eng)
            result = eng.generate(ctx)
            if not result.glb_path.exists() or result.glb_path.stat().st_size == 0:
                raise RuntimeError("engine produced no GLB file")
            meta = {**result.meta, "seconds": round(time.time() - started, 1), "worker_version": __version__,
                    **{k: v for k, v in self.gpu.items() if k != "hostname"}}
            try:
                import torch
                if torch.cuda.is_available():
                    meta["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1024 ** 3, 2)
                    torch.cuda.reset_peak_memory_stats()
            except ImportError:
                pass
            stop.set()
            self.client.progress(job_id, 99, "\n".join(lines) or None)
            self.client.result(job_id, result.glb_path, meta)
            log.info("[%s] uploaded %s (%.0fs)", job_id[:8], result.glb_path.name, meta["seconds"])
        except JobCancelled:
            stop.set()
            log.info("[%s] cancelled", job_id[:8])
        except EngineUnavailable as exc:
            stop.set()
            self._fail(job_id, f"{code} not usable on {self.cfg.worker_id}: {exc}", lines, retryable=True)
            self.engines.pop(code, None)  # stop claiming this engine here
        except Exception as exc:  # noqa: BLE001
            stop.set()
            self._fail(job_id, f"{exc.__class__.__name__}: {exc}", lines + [traceback.format_exc()[-4000:]],
                       retryable=not isinstance(exc, (ValueError,)))
            if "out of memory" in str(exc).lower():
                for c in list(self.loaded):
                    self.loaded.pop(c).unload()
        finally:
            stop.set()
            if not self.cfg.keep_work_files:
                shutil.rmtree(work, ignore_errors=True)

    def _fail(self, job_id: str, error: str, lines: list[str], retryable: bool) -> None:
        log.error("[%s] %s", job_id[:8], error)
        try:
            self.client.fail(job_id, error, "\n".join(lines) or None, retryable)
        except Exception as exc:  # noqa: BLE001
            log.error("could not report failure: %s", exc)

    # ------------------------------------------------------------------ loop
    def serve(self, once: bool = False) -> None:
        engines = list(self.engines)
        info = self.client.hello(engines, self.gpu)
        log.info("connected to %s as %s; engines: %s", self.cfg.studio_url, info["worker_id"], ", ".join(engines))
        while True:
            job = None
            try:
                with gpu_lock(self.cfg.gpu_lock_file, self.needs_gpu):
                    job = self.client.claim(list(self.engines), self.gpu)
                    if job:
                        log.info("claimed job %s (%s, %d image(s))", job["job_id"], job["engine"], len(job["inputs"]))
                        self.run_job(job)
            except httpx.HTTPError as exc:
                log.warning("studio not reachable: %s", exc)
            if not self.engines:
                raise SystemExit("all engines became unavailable")
            if once and job is None:
                return
            if job is None:
                time.sleep(self.cfg.poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Naqshkaar 3D generation worker")
    parser.add_argument("--once", action="store_true", help="exit when the queue is empty")
    parser.add_argument("--list-engines", action="store_true", help="show engines and whether they are usable here")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.list_engines:
        for code, cls in sorted(REGISTRY.items()):
            ok, why = cls().available()
            print(f"{code:14} {'ready' if ok else 'unavailable'}  {'' if ok else why}")
        return
    cfg = WorkerConfig()
    cfg.validate()
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    Worker(cfg).serve(once=args.once)


if __name__ == "__main__":
    main()
