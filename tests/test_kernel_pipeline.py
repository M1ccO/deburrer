import pytest

from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.domain.models import Operation, ToolDefinition, ToolKind
from fc_deburr.machine.profiles import MachineProfile


@pytest.mark.parametrize("kind", [ToolKind.CHAMFER, ToolKind.BALL])
def test_kernel_pipeline_realizes_true_indexed_posture(
    circular_feature, kind
):
    if kind is ToolKind.CHAMFER:
        tool = ToolDefinition(
            id="C90",
            kind=kind,
            diameter=6.0,
            stickout=20.0,
            included_angle_deg=90.0,
            contact_radius=0.5,
        )
        operation = Operation(
            id="chamfer",
            tool_id=tool.id,
            target_width=0.5,
            lead_in_length=1.0,
            lead_out_length=1.0,
        )
    else:
        tool = ToolDefinition(
            id="B6",
            kind=kind,
            diameter=6.0,
            stickout=20.0,
        )
        operation = Operation(
            id="ball",
            tool_id=tool.id,
            ball_engagement=0.25,
            lead_in_length=1.0,
            lead_out_length=1.0,
        )
    profile = MachineProfile(b_min_deg=-180.0, b_max_deg=180.0)

    result = calculate_toolpath(
        circular_feature, tool, operation, profile
    )

    assert result.validation.ok
    cut_model = [
        point
        for point in result.model_path.points
        if point.motion.value == "cut"
    ]
    cut_machine = [
        point
        for point in result.machine_path.points
        if point.motion.value == "cut"
    ]
    assert len(
        {
            tuple(round(value, 9) for value in point.tool_axis)
            for point in cut_model
        }
    ) == 1
    assert len({round(point.b_deg, 9) for point in cut_machine}) == 1
    assert len({round(point.c_deg, 9) for point in cut_machine}) == 1
    assert all(point.contact_xyz is not None for point in cut_model)


def test_default_pipeline_reports_collision_as_not_checked(
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
    )

    result = calculate_toolpath(
        circular_feature,
        tool,
        operation,
        MachineProfile(b_min_deg=-180.0, b_max_deg=180.0),
    )

    diagnostic = next(
        item
        for item in result.kernel_diagnostics
        if item.code == "collision.not_checked"
    )
    assert diagnostic.severity == "warning"
    assert result.selection_total_cost >= 0.0
