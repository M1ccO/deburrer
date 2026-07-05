from __future__ import annotations

import math

from ..domain.errors import GeometryError
from ..domain.models import (
    FaceRegion,
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
    normalize,
    rotate_about_axis,
    scale,
    sub,
)

try:
    import FreeCAD as App
    import Part
except ImportError:
    App = None
    Part = None


def ball_stepover(radius: float, scallop_height: float) -> float:
    if radius <= 0.0:
        raise GeometryError("Ball radius must be positive")
    if not 0.0 < scallop_height < radius:
        raise GeometryError("Surface tolerance must be between zero and ball radius")
    return 2.0 * math.sqrt(2.0 * radius * scallop_height - scallop_height**2)


def solve_face_finish(
    region: FaceRegion,
    tool: ToolDefinition,
    operation: Operation,
) -> Toolpath:
    """Create normal-offset zigzag passes over selected face snapshots."""

    if Part is None or App is None:
        raise RuntimeError("Face finishing requires FreeCAD Python")
    if tool.kind is not ToolKind.BALL:
        raise GeometryError("Face Finishing currently requires a ball end mill")
    if operation.path_sample_spacing <= 0.0:
        raise GeometryError("Path sample spacing must be positive")
    radius = tool.diameter * 0.5
    stepover = ball_stepover(radius, operation.surface_tolerance)

    all_passes = []
    for patch in region.patches:
        face = _face_from_brep(patch.brep)
        all_passes.extend(
            _sample_face_passes(
                face,
                stepover,
                operation.path_sample_spacing,
                operation.surface_direction,
            )
        )
    if not all_passes:
        raise GeometryError("Selected faces did not produce any finishing passes")

    points = []
    for pass_index, samples in enumerate(all_passes):
        if pass_index % 2:
            samples = tuple(reversed(samples))
        cutter_points = []
        for sample_index, (contact, normal) in enumerate(samples):
            previous = samples[max(0, sample_index - 1)][0]
            following = samples[min(len(samples) - 1, sample_index + 1)][0]
            tangent = normalize(sub(following, previous), "surface pass tangent")
            axis = normal
            side = normalize(cross(tangent, normal), "surface posture side")
            if operation.lead_deg:
                axis = rotate_about_axis(axis, side, operation.lead_deg)
            if operation.tilt_deg:
                axis = rotate_about_axis(axis, tangent, operation.tilt_deg)
            axis = normalize(axis)
            ball_center = add(contact, scale(normal, radius))
            tool_tip = sub(ball_center, scale(axis, radius))
            cutter_points.append((tool_tip, contact, axis, tangent))

        first_tip, first_contact, first_axis, first_tangent = cutter_points[0]
        last_tip, last_contact, last_axis, last_tangent = cutter_points[-1]
        pass_flag = "pass=%d" % pass_index
        safe_start = add(first_tip, scale(first_axis, operation.safety_lift))
        safe_end = add(last_tip, scale(last_axis, operation.safety_lift))
        points.extend(
            (
                PathPoint(
                    seq=len(points),
                    xyz=safe_start,
                    tool_axis=first_axis,
                    motion=MotionKind.RAPID,
                    tangent=first_tangent,
                    flags=(pass_flag, "safe_start"),
                ),
                PathPoint(
                    seq=len(points) + 1,
                    xyz=first_tip,
                    tool_axis=first_axis,
                    motion=MotionKind.APPROACH,
                    contact_xyz=first_contact,
                    tangent=first_tangent,
                    feed=operation.feed,
                    flags=(pass_flag, "approach"),
                ),
            )
        )
        for tool_tip, contact, axis, tangent in cutter_points:
            points.append(
                PathPoint(
                    seq=len(points),
                    xyz=tool_tip,
                    tool_axis=axis,
                    motion=MotionKind.CUT,
                    contact_xyz=contact,
                    tangent=tangent,
                    feed=operation.feed,
                    flags=(pass_flag, "surface_finish"),
                )
            )
        points.append(
            PathPoint(
                seq=len(points),
                xyz=safe_end,
                tool_axis=last_axis,
                motion=MotionKind.RETRACT,
                tangent=last_tangent,
                flags=(pass_flag, "safe_end"),
            )
        )

    return Toolpath(
        feature_id=region.id,
        operation_id=operation.id,
        tool_id=tool.id,
        points=tuple(points),
        warnings=(
            "Face finishing: %d passes, calculated stepover %.4f mm "
            "for %.4f mm scallop tolerance"
            % (len(all_passes), stepover, operation.surface_tolerance),
        ),
        source_center_xyz=region.center_xyz,
    )


def _face_from_brep(brep):
    shape = Part.Shape()
    shape.importBrepFromString(brep)
    if len(shape.Faces) != 1:
        raise GeometryError("Face patch BREP does not contain exactly one face")
    return shape.Faces[0]


def _sample_face_passes(face, stepover, sample_spacing, requested_direction):
    u_min, u_max, v_min, v_max = face.ParameterRange
    u_mid = (u_min + u_max) * 0.5
    v_mid = (v_min + v_max) * 0.5
    length_u = face.Surface.vIso(v_mid).toShape(u_min, u_max).Length
    length_v = face.Surface.uIso(u_mid).toShape(v_min, v_max).Length
    if requested_direction not in ("auto", "u", "v"):
        raise GeometryError("Surface direction must be auto, u, or v")
    path_direction = requested_direction
    if path_direction == "auto":
        path_direction = "u" if length_u >= length_v else "v"

    cross_length = length_v if path_direction == "u" else length_u
    cross_count = max(2, int(math.ceil(cross_length / stepover)) + 1)
    passes = []
    for cross_index in range(cross_count):
        fraction = cross_index / (cross_count - 1)
        if path_direction == "u":
            fixed = v_min + (v_max - v_min) * fraction
            path_min, path_max = u_min, u_max
            curve_length = face.Surface.vIso(fixed).toShape(u_min, u_max).Length
        else:
            fixed = u_min + (u_max - u_min) * fraction
            path_min, path_max = v_min, v_max
            curve_length = face.Surface.uIso(fixed).toShape(v_min, v_max).Length
        sample_count = max(3, int(math.ceil(curve_length / sample_spacing)) + 1)
        current = []
        for sample_index in range(sample_count):
            path_parameter = path_min + (path_max - path_min) * (
                sample_index / (sample_count - 1)
            )
            u, v = (
                (path_parameter, fixed)
                if path_direction == "u"
                else (fixed, path_parameter)
            )
            if face.isPartOfDomain(u, v):
                point = face.valueAt(u, v)
                normal = face.normalAt(u, v)
                current.append(
                    (
                        (float(point.x), float(point.y), float(point.z)),
                        normalize(
                            (float(normal.x), float(normal.y), float(normal.z))
                        ),
                    )
                )
            elif len(current) >= 2:
                passes.append(tuple(current))
                current = []
            else:
                current = []
        if len(current) >= 2:
            passes.append(tuple(current))
    return passes
