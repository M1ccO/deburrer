"""Tool holder models.

Generates triangulated meshes of tool holders (shanks) for collision
checking against the workpiece and fixtures.  The holder is modeled as
an axisymmetric body composed of:

1. Taper cone (top section)
2. Cylindrical body
3. Nose reduction (lower section)
4. Optional flange/collar

For MVP, the holder is generated as a parametric mesh.  STEP-based
holders can be added by importing STEP geometry and tessellating it
via the OCCT module.

Usage::

    from cam_kernel.tools.holder_models import build_holder_mesh

    vertices, triangles = build_holder_mesh(
        taper="BT40",
        body_diameter=50.0,
        gauge_length=65.0,
        nose_diameter=30.0,
        nose_length=20.0,
        segments=24,
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

Vec3 = Tuple[float, float, float]


@dataclass
class HolderSpec:
    taper: str = "BT40"
    gauge_length: float = 65.0
    body_diameter: float = 50.0
    nose_diameter: float = 30.0
    nose_length: float = 20.0
    collar_diameter: float = 63.0
    collar_length: float = 8.0
    segments: int = 24


def build_holder_mesh(spec: HolderSpec = HolderSpec()) -> Tuple[List[Vec3], List[Tuple[int, int, int]]]:
    """Build a triangulated mesh of a tool holder.

    The holder is built along the Z axis with the cutting-tool end at
    the origin (Z=0) and the spindle end at Z = total_length.

    Coordinate system:
    - Z: along the holder axis (forward = tool direction)
    - X, Y: radial

    Returns:
        (vertices, triangles) — flat list of (x, y, z) tuples and
        (i, j, k) triangle index tuples.
    """
    vertices = []
    triangles = []

    if spec.body_diameter < spec.nose_diameter:
        raise ValueError("body_diameter must be >= nose_diameter")

    n = max(8, spec.segments)
    half_body = spec.body_diameter * 0.5
    half_nose = spec.nose_diameter * 0.5
    half_collar = spec.collar_diameter * 0.5

    z_nose_top = spec.nose_length
    z_body_bottom = z_nose_top
    z_body_top = z_body_bottom + spec.gauge_length
    z_collar_top = z_body_top + spec.collar_length

    rings = []

    rings.append((0.0, half_nose, spec.nose_length))  # Bottom: nose tip (flat)
    rings.append((z_nose_top, half_nose, spec.nose_length))  # Top of nose, start of body
    rings.append((z_body_top, half_body, spec.gauge_length))  # Top of body
    rings.append((z_collar_top, half_collar, spec.collar_length))  # Top of collar (spindle end)

    for z, radius, _ in rings:
        for i in range(n):
            theta = 2.0 * math.pi * i / n
            x = radius * math.cos(theta)
            y = radius * math.sin(theta)
            vertices.append((x, y, z))

    def ring_offset(ring_idx: int) -> int:
        return ring_idx * n

    for r in range(len(rings) - 1):
        a0 = ring_offset(r)
        a1 = ring_offset(r + 1)
        for i in range(n):
            j = (i + 1) % n
            i0 = a0 + i
            i1 = a0 + j
            i2 = a1 + j
            i3 = a1 + i
            triangles.append((i0, i1, i2))
            triangles.append((i0, i2, i3))

    base_center_idx = len(vertices)
    vertices.append((0.0, 0.0, 0.0))
    for i in range(n):
        j = (i + 1) % n
        triangles.append((base_center_idx, j, i))

    return vertices, triangles


def holder_length(spec: HolderSpec = HolderSpec()) -> float:
    """Total length of the holder along Z."""
    return spec.nose_length + spec.gauge_length + spec.collar_length
