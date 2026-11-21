"""Mesh conversion helpers shared by the engine adapters."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def rotation(rx_deg: float = 0, ry_deg: float = 0, rz_deg: float = 0) -> np.ndarray:
    import trimesh

    m = np.eye(4)
    for deg, axis in ((rx_deg, [1, 0, 0]), (ry_deg, [0, 1, 0]), (rz_deg, [0, 0, 1])):
        if deg:
            m = trimesh.transformations.rotation_matrix(math.radians(deg), axis) @ m
    return m


def to_glb(src, out: Path, rotate_deg: tuple[float, float, float] = (0, 0, 0)) -> Path:
    """Convert a trimesh object or a mesh file (obj/ply/glb/gltf/stl) to a GLB with embedded textures.

    ``rotate_deg`` turns the model into glTF convention (+Y up) for engines that output Z-up.
    """
    import trimesh

    if isinstance(src, (str, Path)):
        obj = trimesh.load(str(src), force="scene")
    else:
        obj = src
    scene = obj if isinstance(obj, trimesh.Scene) else trimesh.Scene(obj)
    if any(rotate_deg):
        scene.apply_transform(rotation(*rotate_deg))
    out.parent.mkdir(parents=True, exist_ok=True)
    data = scene.export(file_type="glb")
    out.write_bytes(data)
    return out


def has_transparency(path: Path) -> bool:
    from PIL import Image

    with Image.open(path) as im:
        if im.mode != "RGBA":
            return False
        lo, _ = im.getchannel("A").getextrema()
        return lo < 250
