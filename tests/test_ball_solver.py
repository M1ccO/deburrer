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
