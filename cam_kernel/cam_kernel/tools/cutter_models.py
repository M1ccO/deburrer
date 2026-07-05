"""Cutter geometry models.

Implements signed-distance functions and contact-point queries for
standard milling cutters.  Each cutter type provides methods required
by the contact solver:

- ``cutter_center(contact_point, tool_axis)`` — compute cutter reference
  (ball center or chamfer tip) from a contact point on the part
- ``tangency_constraint`` — conditions that a valid chamfer posture
  must satisfy

These are pure geometric functions; they do not reference OCCT, FreeCAD,
or any external library beyond the vector math utilities.

Bridges to ``fc_deburr.solver.ball`` and ``fc_deburr.solver.chamfer``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


class CutterKind(str, Enum):
    BALL = "ball"
    CHAMFER = "chamfer"
    BULL = "bull"
    FLAT = "flat"


@dataclass(frozen=True)
class CutterParams:
    kind: CutterKind
    diameter: float
    stickout: float
    tip_radius: float = 0.0
    corner_radius: float = 0.0
    included_angle_deg: Optional[float] = None
    tip_flat_diameter: float = 0.0
    cutting_length: float = 0.0

    @property
    def radius(self) -> float:
        return self.diameter * 0.5


def ball_center_from_contact(contact_xyz: Vec3, tool_axis: Vec3, radius: float) -> Vec3:
    """Cutter reference (ball center) for a ball tool.

    The ball center is ``radius`` above the contact point along the
    tool axis direction.

    Bridges to ``fc_deburr.solver.ball.solve_ball_cut`` math.
    """
    from fc_deburr.geometry.vectors import add, normalize, scale

    axis = normalize(tool_axis)
    return add(contact_xyz, scale(axis, radius))


def chamfer_cone_slope_deg(included_angle_deg: float) -> float:
    """Half-angle of a chamfer cone."""
    return 90.0 - included_angle_deg * 0.5


def chamfer_tangency_check(tool_axis: Vec3, cone_normal: Vec3, slope_deg: float) -> bool:
    """Check whether a tool axis satisfies cone-plane tangency.

    The tool axis must make exactly ``slope_deg`` with every plane
    normal the chamfer face contacts.

    Bridges to ``fc_deburr.solver.chamfer.solve_chamfer_cut`` math.
    """
    from fc_deburr.geometry.vectors import angle_deg
    import math

    actual = angle_deg(tool_axis, cone_normal)
    return abs(actual - slope_deg) < 1.0e-6
