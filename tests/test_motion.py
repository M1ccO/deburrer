from dataclasses import replace

import pytest

from fc_deburr.domain.models import (
    MotionKind,
    Operation,
    PositioningMode,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.geometry.vectors import dot, length, sub
from fc_deburr.solver.chamfer import solve_chamfer_cut
from fc_deburr.solver.motion import add_approach_and_retract


def test_approach_is_tangent_and_tool_axis_based(circular_feature):
    tool = ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=20.0,
        included_angle_deg=90.0,
        contact_radius=0.5,
    )
    operation = Operation(
        id="op",
        tool_id=tool.id,
        target_width=0.5,
        lead_in_length=2.0,
        lead_out_length=3.0,
        safety_lift=4.0,
    )
    cut = solve_chamfer_cut(circular_feature, tool, operation)
    path = add_approach_and_retract(cut, operation)

    assert path.points[0].motion is MotionKind.RAPID
    assert path.points[1].motion is MotionKind.APPROACH
    assert path.points[2].motion is MotionKind.CUT
    assert path.points[-1].motion is MotionKind.RETRACT
    assert path.points[0].xyz != (0.0, 0.0, 0.0)
    assert path.points[1].xyz != circular_feature.samples[0].position


def test_center_positioning_uses_center_to_c0_approach_direction(
    circular_feature,
):
    centered = replace(circular_feature, center_xyz=(0.0, 0.0, 0.0))
    tool = ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=20.0,
        included_angle_deg=90.0,
        contact_radius=0.5,
    )
    operation = Operation(
        id="center",
        tool_id=tool.id,
        target_width=0.5,
        positioning_mode=PositioningMode.CENTER,
        lead_in_length=2.0,
    )
    cut = solve_chamfer_cut(centered, tool, operation)
    path = add_approach_and_retract(cut, operation)
    approach = path.points[1]
    first_cut = path.points[2]
    radial = sub(first_cut.contact_xyz, centered.center_xyz)
    move_to_cut = sub(first_cut.xyz, approach.xyz)

    assert length(move_to_cut) == pytest.approx(2.0)
    assert dot(move_to_cut, radial) > 0.0
