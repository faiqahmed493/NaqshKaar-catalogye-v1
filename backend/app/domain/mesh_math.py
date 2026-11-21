"""Geometry helpers for asset qualification (FR-3D-002, NFR-ACC-002, §6.2).

Only numpy is needed, so these are unit-testable without trimesh. Convention is
glTF: +Y up, X = product width, Z = product depth, front faces +Z.
"""
from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass

import numpy as np

AXIS_INDEX = {"width": 0, "height": 1, "depth": 2}


def extent_tolerance_m(d: float, min_tol: float = 0.005, rel_tol: float = 0.01) -> float:
    """NFR-ACC-002: each extent within max(0.005 m, 0.01·d) of the recorded dimension d."""
    return max(min_tol, rel_tol * d)


def within_tolerance(measured: float, expected: float, min_tol: float = 0.005, rel_tol: float = 0.01) -> bool:
    return abs(measured - expected) <= extent_tolerance_m(expected, min_tol, rel_tol) + 1e-12


def bounds(vertices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if vertices.size == 0:
        raise ValueError("mesh has no vertices")
    return vertices.min(axis=0), vertices.max(axis=0)


def is_finite(vertices: np.ndarray) -> bool:
    return bool(vertices.size) and bool(np.isfinite(vertices).all())


def rotation_matrix_deg(rx: float, ry: float, rz: float) -> np.ndarray:
    """4×4 rotation applied in X, then Y, then Z order (degrees)."""
    def rot(axis: int, deg: float) -> np.ndarray:
        r = math.radians(deg)
        c, s = round(math.cos(r), 12), round(math.sin(r), 12)
        m = np.eye(4)
        if axis == 0:
            m[1:3, 1:3] = [[c, -s], [s, c]]
        elif axis == 1:
            m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
        else:
            m[0:2, 0:2] = [[c, -s], [s, c]]
        return m
    return rot(2, rz) @ rot(1, ry) @ rot(0, rx)


def apply_transform(vertices: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homo = np.hstack([vertices, np.ones((vertices.shape[0], 1))])
    return (homo @ matrix.T)[:, :3]


def choose_yaw_quarter_turns(ext_x: float, ext_z: float, width: float, depth: float,
                             min_ratio_gap: float = 0.05) -> int:
    """Return 1 if a 90° turn about Y matches the footprint better (width along X), else 0.

    Front/back (0° vs 180°) cannot be told from extents; the reviewer fixes that.
    Square-ish targets never trigger a turn.
    """
    if min(ext_x, ext_z, width, depth) <= 0:
        return 0
    target = math.log(width / depth)
    if abs(target) < min_ratio_gap:
        return 0
    native = math.log(ext_x / ext_z)
    return 1 if abs(native + target) < abs(native - target) else 0


@dataclass
class ScalePlan:
    matrix: np.ndarray                # 4×4: translate to floor/centre, then scale
    factors: dict[str, float]         # per axis
    distortion: float                 # max(factor) / min(factor)
    native_extents: dict[str, float]  # x, y, z before scaling


def plan_metric_scale(vertices: np.ndarray, width: float, depth: float, height: float) -> ScalePlan:
    """Centre the footprint on the origin, put the base on y = 0 and scale each axis to W/H/D."""
    lo, hi = bounds(vertices)
    ext = hi - lo
    if (ext <= 1e-9).any():
        raise ValueError("degenerate extent on at least one axis")
    centre = (lo + hi) / 2.0
    translate = np.eye(4)
    translate[:3, 3] = [-centre[0], -lo[1], -centre[2]]
    sx, sy, sz = width / ext[0], height / ext[1], depth / ext[2]
    scale = np.diag([sx, sy, sz, 1.0])
    factors = {"width": float(sx), "height": float(sy), "depth": float(sz)}
    distortion = max(factors.values()) / min(factors.values())
    return ScalePlan(scale @ translate, factors, float(distortion),
                     {"x": float(ext[0]), "y": float(ext[1]), "z": float(ext[2])})


def extents_by_axis(vertices: np.ndarray) -> dict[str, float]:
    lo, hi = bounds(vertices)
    e = hi - lo
    return {"width": float(e[0]), "height": float(e[1]), "depth": float(e[2])}


# --------------------------------------------------------------------------- GLB container
GLB_MAGIC = 0x46546C67  # 'glTF'
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def parse_glb(data: bytes) -> tuple[dict, int]:
    """Return (glTF JSON, binary chunk length). Raises ValueError for a malformed container."""
    if len(data) < 20:
        raise ValueError("file too small to be GLB")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("not a GLB file (bad magic)")
    if version != 2:
        raise ValueError(f"GLB version {version}; glTF 2.0 required")
    if length != len(data):
        raise ValueError("GLB length header does not match file size")
    offset, gltf, bin_len = 12, None, 0
    while offset < length:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset:offset + chunk_len]
        if chunk_type == CHUNK_JSON:
            gltf = json.loads(chunk.decode("utf-8").rstrip(" \x00"))
        elif chunk_type == CHUNK_BIN:
            bin_len = chunk_len
        offset += chunk_len
    if gltf is None:
        raise ValueError("GLB has no JSON chunk")
    return gltf, bin_len


def external_resources(gltf: dict) -> list[str]:
    """List any resource the GLB does not carry inside itself (IR-SW-002 self-containment)."""
    problems: list[str] = []
    for i, buf in enumerate(gltf.get("buffers", [])):
        uri = buf.get("uri")
        if uri and not uri.startswith("data:"):
            problems.append(f"buffer {i} points to external '{uri}'")
        if i > 0 and not uri:
            problems.append(f"buffer {i} has no data")
    for i, img in enumerate(gltf.get("images", [])):
        uri = img.get("uri")
        if uri and not uri.startswith("data:"):
            problems.append(f"image {i} points to external '{uri}'")
        if not uri and "bufferView" not in img:
            problems.append(f"image {i} has no data")
    return problems


def count_triangles(gltf: dict) -> int | None:
    """Triangle count from accessor counts (mode 4 primitives). None if not derivable."""
    accessors = gltf.get("accessors", [])
    total = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                total += accessors[prim["indices"]]["count"] // 3
            elif "POSITION" in prim.get("attributes", {}):
                total += accessors[prim["attributes"]["POSITION"]]["count"] // 3
    return total
