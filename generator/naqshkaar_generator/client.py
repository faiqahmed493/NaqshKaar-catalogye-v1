"""HTTP client for the studio's worker API."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import WorkerConfig


class StudioClient:
    def __init__(self, cfg: WorkerConfig):
        self.cfg = cfg
        self.http = httpx.Client(base_url=cfg.studio_url, timeout=cfg.request_timeout, verify=cfg.verify_tls,
                                 headers={"X-API-Key": cfg.api_key, "User-Agent": f"naqshkaar-generator/{__version__}"})

    def _identity(self, engines: list[str], gpu: dict[str, Any]) -> dict[str, Any]:
        return {"worker_id": self.cfg.worker_id, "engines": engines, "version": __version__,
                "hostname": gpu.get("hostname"), "gpu_name": gpu.get("gpu_name"), "gpu_vram_gb": gpu.get("gpu_vram_gb")}

    def _post(self, path: str, **kw) -> httpx.Response:
        for attempt in range(5):
            try:
                r = self.http.post(path, **kw)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=r.request, response=r)
                return r
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")

    def hello(self, engines: list[str], gpu: dict[str, Any]) -> dict[str, Any]:
        r = self._post("/api/worker/hello", json=self._identity(engines, gpu))
        r.raise_for_status()
        return r.json()

    def claim(self, engines: list[str], gpu: dict[str, Any]) -> dict[str, Any] | None:
        r = self._post("/api/worker/claim", json=self._identity(engines, gpu))
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def progress(self, job_id: str, progress: float | None = None, log: str | None = None) -> dict[str, Any]:
        r = self._post(f"/api/worker/jobs/{job_id}/progress",
                       json={"worker_id": self.cfg.worker_id, "progress": progress, "log": log})
        r.raise_for_status()
        return r.json()

    def result(self, job_id: str, glb: Path, meta: dict[str, Any]) -> dict[str, Any]:
        data = glb.read_bytes()   # bytes, not a file handle, so a retried request resends the whole file
        r = self._post(f"/api/worker/jobs/{job_id}/result",
                       data={"worker_id": self.cfg.worker_id, "meta": json.dumps(meta)},
                       files={"file": (glb.name, data, "model/gltf-binary")})
        r.raise_for_status()
        return r.json()

    def fail(self, job_id: str, error: str, log: str | None = None, retryable: bool = True) -> None:
        r = self._post(f"/api/worker/jobs/{job_id}/fail",
                       json={"worker_id": self.cfg.worker_id, "error": error, "log": log, "retryable": retryable})
        r.raise_for_status()

    def download(self, url: str, dest: Path) -> Path:
        """Inputs come as signed, path-relative URLs (/api/files/...); absolute URLs also work."""
        with self.http.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        return dest
