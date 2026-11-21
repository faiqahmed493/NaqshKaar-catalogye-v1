"""Worker configuration from environment variables (or a .env file next to where you start it)."""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")   # allow trailing comments
        os.environ.setdefault(key.strip(), value)


_load_dotenv(Path.cwd() / ".env")


def _default_lock() -> str:
    import tempfile
    return str(Path(tempfile.gettempdir()) / "naqshkaar-gpu.lock")


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class WorkerConfig:
    studio_url: str = field(default_factory=lambda: (env("STUDIO_URL", "http://localhost:8000") or "").rstrip("/"))
    api_key: str = field(default_factory=lambda: env("STUDIO_API_KEY", "") or "")
    worker_id: str = field(default_factory=lambda: env("WORKER_ID", f"{socket.gethostname()}-{os.getpid()}"))
    engines: list[str] = field(default_factory=lambda: [e.strip() for e in (env("ENGINES", "mock") or "").split(",")
                                                         if e.strip()])
    work_dir: Path = field(default_factory=lambda: Path(env("WORK_DIR", "./work")).resolve())
    poll_seconds: float = field(default_factory=lambda: float(env("POLL_SECONDS", "5")))
    heartbeat_seconds: float = field(default_factory=lambda: float(env("HEARTBEAT_SECONDS", "30")))
    keep_work_files: bool = field(default_factory=lambda: env("KEEP_WORK_FILES", "false").lower() == "true")
    # Set GPU_LOCK_FILE to an empty value to disable the lock.
    gpu_lock_file: str | None = field(default_factory=lambda: os.environ.get("GPU_LOCK_FILE",
                                                                             _default_lock()) or None)
    max_loaded_engines: int = field(default_factory=lambda: int(env("MAX_LOADED_ENGINES", "1")))
    request_timeout: float = field(default_factory=lambda: float(env("REQUEST_TIMEOUT", "120")))
    verify_tls: bool = field(default_factory=lambda: env("VERIFY_TLS", "true").lower() != "false")

    def validate(self) -> None:
        if not self.api_key.startswith("nqk_"):
            raise SystemExit("STUDIO_API_KEY is missing or malformed. Create one with scope 'worker' in the studio.")
        if not self.engines:
            raise SystemExit("ENGINES is empty. Example: ENGINES=trellis or ENGINES=triposr,sf3d")
