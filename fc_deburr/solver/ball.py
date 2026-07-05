from __future__ import annotations

import math
from dataclasses import replace

from ..domain.errors import GeometryError
from ..domain.models import (
    FeatureLoop,
    MotionKind,
    Operation,
    PathPoint,
    ToolDefinition,
    ToolKind,
    Toolpath,
)
from ..geometry.vectors import (
    add,
    cross,
    dot,
    normalize,
    project_onto_plane,
    rotate_about_axis,
    scale,
    sub,
)
from .common import validate_common_inputs


def solve_ball_cut(
    loop: FeatureLoop, tool: ToolDefinition, operation: Operation
) -> Toolpath:
    """Return a ball-tip path for a rounded edge break.

    Engagement moves the ball center inward from first contact with the source
    edge.  The operation intentionally does not claim to create a flat chamfer.
    """

    validate_common_inputs(loop, tool)
    if tool.kind is not ToolKind.BALL:
        raise GeometryError("Ball solver requires a ball tool")
    engagement = operation.ball_engagement
    if engagement is None or engagement <= 0.0:
        raise GeometryError("Ball engagement must be positive")
    radius = tool.diameter * 0.5
    if engagement >= radius:
        raise GeometryError("Ball engagement must be smaller than the ball radius")

    points = []
    extents = []
    for seq, sample in enumerate(loop.samples):
        tangent = normalize(sample.tangent)
        guide = normalize(sample.guide_normal)
        other = normalize(sample.other_normal)
        bisector = normalize(add(guide, other), "edge outward bisector")

        tool_axis = bisector
        side_axis = normalize(cross(tangent, bisector), "ball posture side axis")
        if operation.lead_deg:
            tool_axis = rotate_about_axis(
                tool_axis, side_axis, operation.lead_deg
            )
        if operation.tilt_deg:
            tool_axis = rotate_about_axis(
                tool_axis, tangent, operation.tilt_deg
            )
        tool_axis = normalize(tool_axis)

        center = add(sample.position, scale(bisector, radius - engagement))
        tool_tip = sub(center, scale(tool_axis, radius))

        guide_extent = _predicted_face_extent(
            center, sample.position, guide, other, radius
        )
        other_extent = _predicted_face_extent(
            center, sample.position, other, guide, radius
        )
        guide_inward = normalize(
            project_onto_plane(scale(other, -1.0), guide)
        )
        other_inward = normalize(
            project_onto_plane(scale(guide, -1.0), other)
        )
        extents.append((guide_extent, other_extent))
        points.append(
            PathPoint(
                seq=seq,
                xyz=tool_tip,
                tool_axis=tool_axis,
                motion=MotionKind.CUT,
                contact_xyz=sample.position,
                target_a_xyz=add(
                    sample.position, scale(guide_inward, guide_extent)
                ),
                target_b_xyz=add(
                    sample.position, scale(other_inward, other_extent)
                ),
                tangent=tangent,
                feed=operation.feed,
                flags=(
                    "rounded_break",
                    "guide_extent=%.6f" % guide_extent,
                    "other_extent=%.6f" % other_extent,
                    "source_edge=%s" % sample.source_edge_id,
                ),
            )
        )

    first = points[0]
    points.append(replace(first, seq=len(points), flags=first.flags + ("closure",)))
    minimum_guide = min(pair[0] for pair in extents)
    maximum_guide = max(pair[0] for pair in extents)
    minimum_other = min(pair[1] for pair in extents)
    maximum_other = max(pair[1] for pair in extents)
    warning = (
        "Rounded break predicted face extents: guide %.4f..%.4f mm, "
        "other %.4f..%.4f mm"
        % (minimum_guide, maximum_guide, minimum_other, maximum_other)
    )
    return Toolpath(
        feature_id=loop.id,
        operation_id=operation.id,
        tool_id=tool.id,
        points=tuple(points),
        warnings=(warning,),
        source_center_xyz=loop.center_xyz,
    )


def _predicted_face_extent(center, edge, face_normal, other_normal, radius):
    plane_distance = dot(sub(center, edge), face_normal)
    if plane_distance >= radius:
        return 0.0
    circle_radius = math.sqrt(max(0.0, radius * radius - plane_distance**2))
    inward = normalize(
        project_onto_plane(scale(other_normal, -1.0), face_normal)
    )
    projected_center = dot(sub(center, edge), inward)
    return max(0.0, projected_center + circle_radius)
