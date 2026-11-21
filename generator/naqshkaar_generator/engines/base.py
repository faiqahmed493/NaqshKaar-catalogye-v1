"""Engine adapter contract.

An adapter turns the job's input images into ONE GLB file in glTF convention
(+Y up, metres not required: the studio rescales to the recorded W × D × H).
Heavy libraries are imported inside load()/generate(), so a worker can start in
an environment that only has the engines it is asked to run.
"""
from __future__ import annotations

import os
import sys
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class EngineUnavailable(RuntimeError):
    """Configuration problem on this worker (missing repo, package or key). Not retried on this worker."""


class JobCancelled(RuntimeError):
    pass


@dataclass
class InputImage:
    path: Path
    view_angle: str = "unknown"
    role: str = "gallery"


@dataclass
class JobContext:
    job_id: str
    params: dict[str, Any]
    inputs: list[InputImage]
    work_dir: Path
    target_dimensions_m: dict[str, float | None] | None = None
    product: dict[str, Any] = field(default_factory=dict)
    report: Callable[[float | None, str | None], None] = lambda p, m: None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def step(self, progress: float, message: str) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled("cancelled from the studio")
        self.report(progress, message)

    def param(self, name: str, default: Any = None) -> Any:
        v = self.params.get(name)
        return default if v is None else v


@dataclass
class EngineResult:
    glb_path: Path
    meta: dict[str, Any] = field(default_factory=dict)


class Engine(ABC):
    code: str = ""
    needs_gpu: bool = True

    def __init__(self) -> None:
        self.loaded = False

    def available(self) -> tuple[bool, str]:
        """Cheap check used at worker start; must not load model weights."""
        return True, "ok"

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False
        free_gpu_memory()

    @abstractmethod
    def generate(self, ctx: JobContext) -> EngineResult: ...


def free_gpu_memory() -> None:
    try:
        import gc

        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def require_module(name: str, hint: str) -> None:
    import importlib.util
    if importlib.util.find_spec(name) is None:
        raise EngineUnavailable(f"python module '{name}' not found. {hint}")


def repo_path(env_name: str, hint: str) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        raise EngineUnavailable(f"{env_name} is not set. {hint}")
    p = Path(raw).expanduser().resolve()
    if not p.is_dir():
        raise EngineUnavailable(f"{env_name}={p} does not exist. {hint}")
    return p


def add_to_path(*paths: Path) -> None:
    for p in paths:
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


@contextmanager
def working_dir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def torch_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda:0"
    raise EngineUnavailable("no CUDA GPU visible to PyTorch")


def seed_everything(seed: int) -> None:
    import random

    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
