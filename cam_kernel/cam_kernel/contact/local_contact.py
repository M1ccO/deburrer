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


def ball_contact_on_edge(samples, ball_radius: float, engagement: float) -> Tuple[ContactPoint, ...]:
    """Compute ball-tool contact for each edge sample.

    Delegates to ``fc_deburr.solver.ball`` for the full pipeline and
    extracts just the contact points.
    """
    from fc_deburr.domain.models import (
        FeatureLoop,
        FeatureSample,
        FeatureSourceKind,
        Operation,
        PathPoint,
        ToolDefinition,
        ToolKind,
        MotionKind,
        PositioningMode,
    )
    from fc_deburr.solver.ball import solve_ball_cut

    f_samples = tuple(
        FeatureSample(
            position=s.position,
            tangent=s.tangent,
            guide_normal=s.guide_normal,
            other_normal=s.other_normal,
            source_edge_id=s.edge_id,
        )
        for s in samples
    )
    loop = FeatureLoop(
        id="local_contact",
        samples=f_samples,
        closed=True,
        source_kind=FeatureSourceKind.WIRE,
    )
    tool = ToolDefinition(
        id="ball_local",
        kind=ToolKind.BALL,
        diameter=ball_radius * 2.0,
        stickout=50.0,
        cutting_length=ball_radius * 4.0,
    )
    op = Operation(
        id="local_op",
        tool_id="ball_local",
        ball_engagement=engagement,
        feed=800.0,
        motion_mode=None,  # will be set later
    )
    op = op.__class__(
        **{**op.__dict__, "motion_mode": __import__("fc_deburr.domain.models", fromlist=["MotionMode"]).MotionMode.INDEXED_3_PLUS_2}
    )
    tp = solve_ball_cut(loop, tool, op)
    contact_points = []
    for pt in tp.points:
        if pt.motion == MotionKind.CUT:
            contact_points.append(
                ContactPoint(
                    seq=pt.seq,
                    contact_xyz=pt.contact_xyz if pt.contact_xyz else pt.xyz,
                    tool_axis=pt.tool_axis,
                    cutter_ref_xyz=pt.xyz,
                    kind=ContactKind.BALL,
                    source_tangent=pt.tangent,
                )
            )
    return tuple(contact_points)


def chamfer_contact_on_edge(samples, diameter: float, included_angle_deg: float, width: float) -> Tuple[ContactPoint, ...]:
    """Compute chamfer-tool contact for each edge sample.

    Delegates to ``fc_deburr.solver.chamfer`` for the full pipeline.
    """
    from fc_deburr.domain.models import (
        FeatureLoop,
        FeatureSample,
        FeatureSourceKind,
        Operation,
        ToolDefinition,
        ToolKind,
        MotionKind,
        PositioningMode,
    )
    from fc_deburr.solver.chamfer import solve_chamfer_cut

    f_samples = tuple(
        FeatureSample(
            position=s.position,
            tangent=s.tangent,
            guide_normal=s.guide_normal,
            other_normal=s.other_normal,
            source_edge_id=s.edge_id,
        )
        for s in samples
    )
    loop = FeatureLoop(
        id="local_contact",
        samples=f_samples,
        closed=True,
        source_kind=FeatureSourceKind.WIRE,
    )
    tool = ToolDefinition(
        id="chamfer_local",
        kind=ToolKind.CHAMFER,
        diameter=diameter,
        stickout=50.0,
        included_angle_deg=included_angle_deg,
        tip_flat_diameter=0.2,
    )
    MotionMode = __import__("fc_deburr.domain.models", fromlist=["MotionMode"]).MotionMode
    op = Operation(
        id="local_op",
        tool_id="chamfer_local",
        target_width=width,
        feed=800.0,
        motion_mode=MotionMode.INDEXED_3_PLUS_2,
    )
    tp = solve_chamfer_cut(loop, tool, op)
    contact_points = []
    for pt in tp.points:
        if pt.motion == MotionKind.CUT:
            contact_points.append(
                ContactPoint(
                    seq=pt.seq,
                    contact_xyz=pt.contact_xyz if pt.contact_xyz else pt.xyz,
                    tool_axis=pt.tool_axis,
                    cutter_ref_xyz=pt.xyz,
                    kind=ContactKind.CHAMFER,
                    source_tangent=pt.tangent,
                )
            )
    return tuple(contact_points)
