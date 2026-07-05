from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..domain.errors import GeometryError
from ..domain.models import (
    MotionMode,
    Operation,
    PathPoint,
    ToolDefinition,
    ToolKind,
    Toolpath,
    operation_motion_mode,
)
from ..geometry.vectors import add, dot, normalize, scale, sub
from ..machine.kinematics import (
    _b_for_fixed_c_axis,
    axis_model_from_bc,
    bc_from_axis_model,
)
from ..machine.profiles import MachineProfile

POSTURE_TANGENCY_TOLERANCE = 1.0e-5


@dataclass(frozen=True)
class RealizedPosture:
    path: Toolpath
    indexed_b_deg: float | None
    indexed_c_deg: float | None


def realize_motion_mode(
    analytic_path: Toolpath,
    tool: ToolDefinition,
    operation: Operation,
    profile: MachineProfile,
) -> RealizedPosture:
    mode = operation_motion_mode(operation)
    points = analytic_path.points
    if not points:
        raise GeometryError("Cannot realize an empty cutter path")

    if mode is MotionMode.INDEXED_3_PLUS_2:
        if (
            operation.auto_index
            or operation.indexed_b_deg is None
            or operation.indexed_c_deg is None
        ):
            average_axis = _average_axis(points)
            indexed_b, indexed_c = bc_from_axis_model(
                average_axis, profile
            )
        else:
            indexed_b = operation.indexed_b_deg
            indexed_c = operation.indexed_c_deg
        fixed_axis = axis_model_from_bc(
            indexed_b, indexed_c, profile
        )
        try:
            realized = tuple(
                _realize_point(point, fixed_axis, tool, index, mode)
                for index, point in enumerate(points)
            )
        except GeometryError as error:
            raise GeometryError(
                "Suggested B%.3f C%.3f failed: %s"
                % (indexed_b, indexed_c, error)
            ) from error
        return RealizedPosture(
            replace(analytic_path, points=realized),
            indexed_b,
            indexed_c,
        )

    if mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
        if operation.auto_index or operation.indexed_c_deg is None:
            indexed_c = _mean_c(points, profile)
        else:
            indexed_c = operation.indexed_c_deg
        realized = []
        try:
            for index, point in enumerate(points):
                b_deg = _b_for_fixed_c_axis(
                    point.tool_axis, indexed_c, profile
                )
                axis = axis_model_from_bc(
                    b_deg, indexed_c, profile
                )
                realized.append(
                    _realize_point(point, axis, tool, index, mode)
                )
        except GeometryError as error:
            raise GeometryError(
                "Suggested fixed C%.3f failed: %s"
                % (indexed_c, error)
            ) from error
        return RealizedPosture(
            replace(analytic_path, points=tuple(realized)),
            None,
            indexed_c,
        )

    realized = []
    previous_c = None
    for index, point in enumerate(points):
        b_deg, c_deg = bc_from_axis_model(
            point.tool_axis, profile, previous_c
        )
        previous_c = c_deg
        axis = axis_model_from_bc(b_deg, c_deg, profile)
        realized.append(
            _realize_point(point, axis, tool, index, mode)
        )
    return RealizedPosture(
        replace(analytic_path, points=tuple(realized)),
        None,
        None,
    )


def _realize_point(
    point: PathPoint,
    realized_axis,
    tool: ToolDefinition,
    index: int,
    mode: MotionMode,
) -> PathPoint:
    axis = normalize(realized_axis)
    if tool.kind is ToolKind.BALL:
        radius = tool.diameter * 0.5
        center = add(point.xyz, scale(point.tool_axis, radius))
        xyz = sub(center, scale(axis, radius))
    elif tool.kind is ToolKind.CHAMFER:
        xyz = _realize_chamfer(point, axis, tool, index, mode)
    else:
        raise GeometryError("Unsupported posture tool: %s" % tool.kind)
    return replace(
        point,
        xyz=xyz,
        tool_axis=axis,
        flags=point.flags + ("machine_posture=%s" % mode.value,),
    )


def _realize_chamfer(
    point: PathPoint,
    axis,
    tool: ToolDefinition,
    index: int,
    mode: MotionMode,
):
    if point.contact_xyz is None:
        raise GeometryError(
            "Chamfer posture requires contact geometry at station %d"
            % index
        )
    half_angle = math.radians(tool.included_angle_deg * 0.5)
    sine = math.sin(half_angle)
    cosine = math.cos(half_angle)
    tangent = math.tan(half_angle)
    tip_radius = tool.tip_flat_diameter * 0.5
    contact_radius = tool.contact_radius + tool.radial_correction
    axial_distance = (
        (contact_radius - tip_radius) / tangent
        + tool.axial_correction
    )
    old_radial = normalize(
        scale(
            sub(
                sub(point.contact_xyz, point.xyz),
                scale(point.tool_axis, axial_distance),
            ),
            1.0 / contact_radius,
        ),
        "analytic cone radial",
    )
    chamfer_normal = normalize(
        sub(
            scale(point.tool_axis, sine),
            scale(old_radial, cosine),
        ),
        "analytic chamfer normal",
    )
    error = abs(dot(chamfer_normal, axis) - sine)
    if error > POSTURE_TANGENCY_TOLERANCE:
        raise GeometryError(
            "%s cannot preserve chamfer tangency at station %d "
            "(posture error %.6g); use a more flexible motion mode "
            "or another indexed angle"
            % (mode.value, index, error)
        )
    radial = normalize(
        scale(
            sub(scale(axis, sine), chamfer_normal),
            1.0 / cosine,
        ),
        "realized cone radial",
    )
    return sub(
        sub(point.contact_xyz, scale(axis, axial_distance)),
        scale(radial, contact_radius),
    )


def _average_axis(points):
    vector = tuple(
        sum(point.tool_axis[axis] for point in points)
        for axis in range(3)
    )
    return normalize(vector, "average indexed tool posture")


def _mean_c(points, profile):
    angles = [
        bc_from_axis_model(point.tool_axis, profile)[1]
        for point in points
    ]
    sine = sum(math.sin(math.radians(value)) for value in angles)
    cosine = sum(math.cos(math.radians(value)) for value in angles)
    return math.degrees(math.atan2(sine, cosine))
