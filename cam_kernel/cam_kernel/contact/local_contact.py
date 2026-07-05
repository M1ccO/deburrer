"""Local contact solvers.

Analytic contact solutions for simple cutter-on-part geometries.
These are the primary contact paths for edge deburring:

- **ball_on_edge** — ball endmill touching an edge defined by two faces
- **chamfer_on_edge** — chamfer mill touching an edge with cone tangency
- **face_contact** — ball tool on a single face (surface finishing)

Each solver returns a sequence of ``ContactPoint`` values independent
of any CAD library.  The callers must provide sample points with
position, tangent, and face normals.

Bridges to ``fc_deburr.solver.ball.solve_ball_cut`` and
``fc_deburr.solver.chamfer.solve_chamfer_cut`` for the full solver
pipeline (including approach/retract and motion generation).

TODO:
 - Bull-nose contact on edges
 - Multi-step contact for relief grinding
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


class ContactKind(str, Enum):
    BALL = "ball"
    CHAMFER = "chamfer"
    BULL = "bull"


@dataclass(frozen=True)
class ContactPoint:
    seq: int
    contact_xyz: Vec3
    tool_axis: Vec3
    cutter_ref_xyz: Vec3
    kind: ContactKind
    source_tangent: Optional[Vec3] = None
    guide_normal: Optional[Vec3] = None
    other_normal: Optional[Vec3] = None


def ball_contact_on_edge(
    samples,
    ball_radius: float,
    engagement: float,
    break_width: float = None,
    lead_deg: float = 0.0,
    tilt_deg: float = 0.0,
) -> Tuple[ContactPoint, ...]:
    """Compute ball-tool contact for each edge sample.

    Uses the standalone ball solver from ``solver_core``.
    """
    from .solver_core import solve_ball_cut, BallSolverError

    try:
        results = solve_ball_cut(
            samples,
            ball_radius=ball_radius,
            break_width=break_width,
            ball_engagement=engagement if break_width is None else None,
            lead_deg=lead_deg,
            tilt_deg=tilt_deg,
        )
    except BallSolverError as exc:
        raise ValueError("Ball solve failed: %s" % exc)

    contact_points = []
    for pt in results:
        contact_points.append(
            ContactPoint(
                seq=pt.seq,
                contact_xyz=pt.contact_xyz,
                tool_axis=pt.tool_axis,
                cutter_ref_xyz=pt.xyz,
                kind=ContactKind.BALL,
                source_tangent=pt.tangent,
            )
        )
    return tuple(contact_points)


def chamfer_contact_on_edge(
    samples,
    diameter: float,
    included_angle_deg: float,
    width: float,
    contact_radius: float = 3.0,
    tip_flat_diameter: float = 0.0,
    axial_correction: float = 0.0,
    lead_deg: float = 0.0,
) -> Tuple[ContactPoint, ...]:
    """Compute chamfer-tool contact for each edge sample.

    Uses the standalone chamfer solver from ``solver_core``.
    """
    from .solver_core import solve_chamfer_cut, ChamferSolverError

    try:
        results = solve_chamfer_cut(
            samples,
            included_angle_deg=included_angle_deg,
            contact_radius=contact_radius,
            tip_flat_diameter=tip_flat_diameter,
            target_width=width,
            axial_correction=axial_correction,
            lead_deg=lead_deg,
        )
    except ChamferSolverError as exc:
        raise ValueError("Chamfer solve failed: %s" % exc)

    contact_points = []
    for pt in results:
        contact_points.append(
            ContactPoint(
                seq=pt.seq,
                contact_xyz=pt.contact_xyz,
                tool_axis=pt.tool_axis,
                cutter_ref_xyz=pt.xyz,
                kind=ContactKind.CHAMFER,
                source_tangent=pt.tangent,
            )
        )
    return tuple(contact_points)
