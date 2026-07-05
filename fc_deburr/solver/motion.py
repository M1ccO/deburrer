from __future__ import annotations

from dataclasses import replace

from ..domain.errors import GeometryError
from ..domain.models import (
    MotionKind,
    Operation,
    PathPoint,
    PositioningMode,
    Toolpath,
)
from ..geometry.vectors import add, normalize, scale, sub


def add_approach_and_retract(
    cut_path: Toolpath, operation: Operation
) -> Toolpath:
    cuts = tuple(point for point in cut_path.points if point.motion is MotionKind.CUT)
    if len(cuts) < 2:
        raise GeometryError("Approach generation requires a cutting path")
    first = cuts[0]
    last = cuts[-1]
    if first.tangent is None or last.tangent is None:
        raise GeometryError("Cutting points require tangents")

    first_tangent = normalize(first.tangent)
    last_tangent = normalize(last.tangent)
    if operation.positioning_mode is PositioningMode.CENTER:
        if cut_path.source_center_xyz is None:
            raise GeometryError("Center Positioning requires a wire center")
        first_direction = normalize(
            sub(
                first.contact_xyz or first.xyz,
                cut_path.source_center_xyz,
            ),
            "center approach direction",
        )
        last_direction = normalize(
            sub(
                last.contact_xyz or last.xyz,
                cut_path.source_center_xyz,
            ),
            "center retract direction",
        )
        lead_start = sub(
            first.xyz, scale(first_direction, operation.lead_in_length)
        )
        lead_end = sub(
            last.xyz, scale(last_direction, operation.lead_out_length)
        )
    else:
        lead_start = sub(
            first.xyz, scale(first_tangent, operation.lead_in_length)
        )
        lead_end = add(
            last.xyz, scale(last_tangent, operation.lead_out_length)
        )
    safe_start = add(lead_start, scale(first.tool_axis, operation.safety_lift))
    safe_end = add(lead_end, scale(last.tool_axis, operation.safety_lift))

    owned = [
        PathPoint(
            seq=0,
            xyz=safe_start,
            tool_axis=first.tool_axis,
            motion=MotionKind.RAPID,
            tangent=first.tangent,
            flags=("safe_start",),
        ),
        PathPoint(
            seq=1,
            xyz=lead_start,
            tool_axis=first.tool_axis,
            motion=MotionKind.APPROACH,
            tangent=first.tangent,
            feed=operation.feed,
            flags=("approach",),
        ),
    ]
    owned.extend(replace(point, seq=index + 2) for index, point in enumerate(cuts))
    owned.extend(
        [
            PathPoint(
                seq=len(owned),
                xyz=lead_end,
                tool_axis=last.tool_axis,
                motion=MotionKind.LEAD_OUT,
                tangent=last.tangent,
                feed=operation.feed,
                flags=("lead_out",),
            ),
            PathPoint(
                seq=len(owned) + 1,
                xyz=safe_end,
                tool_axis=last.tool_axis,
                motion=MotionKind.RETRACT,
                tangent=last.tangent,
                flags=("safe_end",),
            ),
        ]
    )
    return Toolpath(
        feature_id=cut_path.feature_id,
        operation_id=cut_path.operation_id,
        tool_id=cut_path.tool_id,
        points=tuple(owned),
        warnings=cut_path.warnings,
        source_center_xyz=cut_path.source_center_xyz,
    )
