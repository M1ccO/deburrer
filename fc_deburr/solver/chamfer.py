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
    dot,
    midpoint,
    normalize,
    project_onto_plane,
    rotate_about_axis,
    scale,
    sub,
)
from .common import validate_common_inputs

TANGENCY_TOLERANCE = 1.0e-6


def solve_chamfer_cut(
    loop: FeatureLoop, tool: ToolDefinition, operation: Operation
) -> Toolpath:
    """Return the ideal cone-tip path for an equal-face-width chamfer.

    The feature samples remain the source of truth.  This function owns only
    the newly created cutter-reference path and never mutates the feature.
    """

    validate_common_inputs(loop, tool)
    if tool.kind is not ToolKind.CHAMFER:
        raise GeometryError("Chamfer solver requires a chamfer tool")
    if not operation.target_width or operation.target_width <= 0.0:
        raise GeometryError("Chamfer width must be positive")
    if not tool.included_angle_deg:
        raise GeometryError("Chamfer tool requires an included angle")
    if not 0.0 < tool.included_angle_deg < 180.0:
        raise GeometryError("Included angle must be between 0 and 180 degrees")
    if abs(operation.tilt_deg) > TANGENCY_TOLERANCE:
        raise GeometryError(
            "Chamfer tilt changes the requested flat chamfer; use lead only "
            "or a calibrated non-flat operation"
        )

    half_angle = math.radians(tool.included_angle_deg * 0.5)
    sin_alpha = math.sin(half_angle)
    cos_alpha = math.cos(half_angle)
    tan_alpha = math.tan(half_angle)
    if abs(cos_alpha) <= TANGENCY_TOLERANCE or abs(tan_alpha) <= TANGENCY_TOLERANCE:
        raise GeometryError("Chamfer tool angle is numerically unstable")

    tip_radius = tool.tip_flat_diameter * 0.5
    contact_radius = tool.contact_radius
    if contact_radius is None:
        raise GeometryError("Chamfer tool requires an explicit contact radius")
    contact_radius += tool.radial_correction
    if contact_radius <= tip_radius:
        raise GeometryError("Contact radius must exceed the tool tip-flat radius")
    if contact_radius >= tool.diameter * 0.5:
        raise GeometryError("Contact radius must be smaller than the tool radius")

    points = []
    for seq, sample in enumerate(loop.samples):
        guide = normalize(sample.guide_normal, "guide-face normal")
        other = normalize(sample.other_normal, "other-face normal")
        chamfer_normal = normalize(add(guide, other), "chamfer normal")

        guide_inward = normalize(
            project_onto_plane(scale(other, -1.0), guide),
            "guide-face inward direction",
        )
        other_inward = normalize(
            project_onto_plane(scale(guide, -1.0), other),
            "other-face inward direction",
        )
        guide_boundary = add(
            sample.position, scale(guide_inward, operation.target_width)
        )
        other_boundary = add(
            sample.position, scale(other_inward, operation.target_width)
        )
        contact = midpoint(guide_boundary, other_boundary)

        # Of all cone axes tangent to the desired chamfer plane, choose the one
        # closest to the selected guide-face normal.  Lead rotates around the
        # plane normal without destroying cone-plane tangency.
        guide_plane_component = normalize(
            project_onto_plane(guide, chamfer_normal),
            "guide-face posture component",
        )
        tool_axis = normalize(
            add(
                scale(chamfer_normal, sin_alpha),
                scale(guide_plane_component, cos_alpha),
            ),
            "chamfer tool axis",
        )
        if operation.lead_deg:
            tool_axis = normalize(
                rotate_about_axis(
                    tool_axis, chamfer_normal, operation.lead_deg
                )
            )

        radial = normalize(
            scale(
                sub(scale(tool_axis, sin_alpha), chamfer_normal),
                1.0 / cos_alpha,
            ),
            "cone contact radial",
        )
        if abs(dot(chamfer_normal, tool_axis) - sin_alpha) > 1.0e-5:
            raise GeometryError("Unable to satisfy cone/chamfer tangency")

        axial_distance = (
            (contact_radius - tip_radius) / tan_alpha
            + tool.axial_correction
        )
        tool_tip = sub(
            sub(contact, scale(tool_axis, axial_distance)),
            scale(radial, contact_radius),
        )
        points.append(
            PathPoint(
                seq=seq,
                xyz=tool_tip,
                tool_axis=tool_axis,
                motion=MotionKind.CUT,
                contact_xyz=contact,
                target_a_xyz=guide_boundary,
                target_b_xyz=other_boundary,
                tangent=normalize(sample.tangent),
                feed=operation.feed,
                flags=(
                    "equal_face_width=%.6f" % operation.target_width,
                    "source_edge=%s" % sample.source_edge_id,
                ),
            )
        )

    # Explicitly close the cut at C0.  This is solver-owned duplication, not a
    # duplicate in the source feature data.
    first = points[0]
    points.append(replace(first, seq=len(points), flags=first.flags + ("closure",)))
    return Toolpath(
        feature_id=loop.id,
        operation_id=operation.id,
        tool_id=tool.id,
        points=tuple(points),
        source_center_xyz=loop.center_xyz,
    )
