"""Engine registry. Add a new engine: subclass Engine, register it here, and add a row to
generation_engine (backend/sql/0003_seed_reference.sql) with the same code."""
from __future__ import annotations

from .base import Engine
from .cli_engines import CommandEngine, InstantMeshEngine
from .hunyuan import Hunyuan3D2Engine, Hunyuan3D2MVEngine, Hunyuan3D21Engine
from .meshy import MeshyEngine
from .mock import MockEngine
from .sf3d import SF3DEngine
from .trellis import TrellisEngine
from .trellis2 import Trellis2Engine
from .trellis_hf import TrellisHFEngine
from .triposr import TripoSREngine

REGISTRY: dict[str, type[Engine]] = {cls.code: cls for cls in (
    MockEngine, TrellisEngine, TrellisHFEngine, Trellis2Engine, TripoSREngine, Hunyuan3D2Engine, Hunyuan3D2MVEngine,
    Hunyuan3D21Engine, SF3DEngine, InstantMeshEngine, CommandEngine, MeshyEngine,
)}
