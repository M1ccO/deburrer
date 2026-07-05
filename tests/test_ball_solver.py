import math

import pytest

from fc_deburr.domain.errors import GeometryError
from fc_deburr.domain.models import Operation, ToolDefinition, ToolKind
from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.solver.ball import solve_ball_cut


def test_ball_operation_reports_rounded_break_extents(circular_feature):
    tool = ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=20.0,
    )
    path = solve_ball_cut(
        circular_feature,
        tool,
        Operation(id="ball", tool_id=tool.id, ball_engagement=0.25),
    )

    assert len(path.points) == len(circular_feature.samples) + 1
    assert path.warnings
    assert "Rounded break predicted face extents" in path.warnings[0]
    assert "rounded_break" in path.points[0].flags


def test_more_ball_engagement_moves_tool_reference(circular_feature):
    tool = ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=20.0,
    )
    shallow = solve_ball_cut(
        circular_feature,
        tool,
        Operation(id="a", tool_id=tool.id, ball_engagement=0.1),
    )
    deep = solve_ball_cut(
        circular_feature,
        tool,
        Operation(id="b", tool_id=tool.id, ball_engagement=0.5),
    )

    assert shallow.points[0].xyz != deep.points[0].xyz
    assert circular_feature.samples[0].position == (10.0, 0.0, 0.0)


def test_ball_path_runs_through_machine_pipeline_when_profile_is_reachable(
    circular_feature,
):
    tool = ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=20.0,
    )
    operation = Operation(
        id="ball",
        tool_id=tool.id,
        ball_engagement=0.25,
        safety_lift=2.0,
    )

    result = calculate_toolpath(
        circular_feature,
        tool,
        operation,
        MachineProfile(b_min_deg=-180.0),
    )

    assert result.validation.ok
    assert result.machine_path.points
    assert result.machine_path.warnings


def test_rounded_break_width_is_measured_along_both_faces(
    circular_feature,
):
    tool = ToolDefinition(
        id="D3",
        kind=ToolKind.BALL,
        diameter=3.0,
        stickout=20.0,
    )
    requested_width = 0.3

    path = solve_ball_cut(
        circular_feature,
        tool,
        Operation(
            id="width",
            tool_id=tool.id,
            ball_break_width=requested_width,
        ),
    )

    for point in path.points[:-1]:
        assert math.dist(
            point.contact_xyz,
            point.target_a_xyz,
        ) == pytest.approx(requested_width, abs=1.0e-9)
        assert math.dist(
            point.contact_xyz,
            point.target_b_xyz,
        ) == pytest.approx(requested_width, abs=1.0e-9)
    assert "requested 0.3000 mm" in path.warnings[0]


def test_rounded_break_width_must_fit_the_ball_radius(
    circular_feature,
):
    tool = ToolDefinition(
        id="D3",
        kind=ToolKind.BALL,
        diameter=3.0,
        stickout=20.0,
    )

    with pytest.raises(GeometryError, match="smaller than the ball radius"):
        solve_ball_cut(
            circular_feature,
            tool,
            Operation(
                id="too-wide",
                tool_id=tool.id,
                ball_break_width=1.5,
            ),
        )


@pytest.mark.parametrize("face_angle_deg", [45.0, 90.0, 120.0])
def test_rounded_break_width_accounts_for_local_face_angle(
    face_angle_deg,
):
    from fc_deburr.domain.models import FeatureLoop, FeatureSample

    angle = math.radians(face_angle_deg)
    samples = tuple(
        FeatureSample(
            position=(0.0, 0.0, float(index)),
            tangent=(0.0, 0.0, 1.0),
            guide_normal=(1.0, 0.0, 0.0),
            other_normal=(math.cos(angle), math.sin(angle), 0.0),
        )
        for index in range(2)
    )
    tool = ToolDefinition(
        id="D3",
        kind=ToolKind.BALL,
        diameter=3.0,
        stickout=20.0,
    )

    path = solve_ball_cut(
        FeatureLoop("angled", samples, closed=False),
        tool,
        Operation(
            id="width",
            tool_id=tool.id,
            ball_break_width=0.3,
        ),
    )

    for point in path.points:
        assert math.dist(
            point.contact_xyz,
            point.target_a_xyz,
        ) == pytest.approx(0.3, abs=1.0e-9)
        assert math.dist(
            point.contact_xyz,
            point.target_b_xyz,
        ) == pytest.approx(0.3, abs=1.0e-9)
