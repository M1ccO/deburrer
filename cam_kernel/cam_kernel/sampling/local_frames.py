"""Local frames — coordinate frames along sampled geometry.

Constructs Darboux frames (tangent, normal, binormal) along edges and
Frenet frames along face paths.  These frames provide the local
coordinate system for:
- Tool-axis seeding from bisector and lead/tilt angles
- Posture candidate generation
- Feed-direction alignment

All frames are pure ``(origin, x_axis, y_axis, z_axis)`` tuples of Vec3
— no OCCT dependency.

Bridges to ``fc_deburr.geometry.vectors`` for vector math.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class LocalFrame:
    origin: Vec3
    x_axis: Vec3
    y_axis: Vec3
    z_axis: Vec3


def edge_bisector_frame(sample) -> LocalFrame:
    """Build a Darboux-style frame from an edge sample.

    x = tangent, y = bisector of guide_normal and other_normal,
    z = cross(x, y).

    Bridges to ``fc_deburr.geometry.vectors`` math.
    """
    from fc_deburr.geometry.vectors import cross, normalize

    tangent = normalize(sample.tangent)
    bisector = normalize(
        (
            sample.guide_normal[0] + sample.other_normal[0],
            sample.guide_normal[1] + sample.other_normal[1],
            sample.guide_normal[2] + sample.other_normal[2],
        )
    )
    z_axis = normalize(cross(tangent, bisector))
    return LocalFrame(
        origin=sample.position,
        x_axis=tangent,
        y_axis=bisector,
        z_axis=z_axis,
    )


def face_tool_axis_frame(sample) -> LocalFrame:
    """Build a tool-axis frame from a face sample.

    z = surface normal (tool points toward surface),
    x and y chosen arbitrarily in the tangent plane.

    TODO: Oriented x/y from pass direction.
    """
    raise NotImplementedError("Face tool-axis frame not yet implemented")
