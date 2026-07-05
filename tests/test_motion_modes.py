from dataclasses import replace

import pytest

from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.domain.errors import ValidationError
from fc_deburr.domain.models import (
    FeatureLoop,
    MotionKind,
    MotionMode,
    Operation,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.machine.kinematics import axis_model_from_bc
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.preview.builder import build_preview
from fc_deburr.ui.settings import migrate_ui_settings


def _ball_tool():
    return ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=20.0,
    )


def _operation(mode, **changes):
    values = dict(
        id="mode",
        tool_id="B6",
        ball_engagement=0.25,
        motion_mode=mode,
    )
    values.update(changes)
    return Operation(**values)


def _cuts(path):
    return [
        point for point in path.points if point.motion is MotionKind.CUT
    ]


def test_true_3_plus_2_has_fixed_b_and_c(circular_feature):
    result = calculate_toolpath(
        circular_feature,
        _ball_tool(),
        _operation(MotionMode.INDEXED_3_PLUS_2),
        MachineProfile(),
    )
    cuts = _cuts(result.machine_path)

    assert len({round(point.b_deg, 9) for point in cuts}) == 1
    assert len({round(point.c_deg, 9) for point in cuts}) == 1
    assert result.indexed_b_deg is not None
    assert result.indexed_c_deg is not None


def test_manual_3_plus_2_angles_are_honored(circular_feature):
    result = calculate_toolpath(
        circular_feature,
        _ball_tool(),
        _operation(
            MotionMode.INDEXED_3_PLUS_2,
            auto_index=False,
            indexed_b_deg=-45.0,
            indexed_c_deg=90.0,
        ),
        MachineProfile(),
    )

    assert {point.b_deg for point in _cuts(result.machine_path)} == {-45.0}
    assert {point.c_deg for point in _cuts(result.machine_path)} == {90.0}


def test_4_plus_1_has_fixed_c_and_varying_b(circular_feature):
    result = calculate_toolpath(
        circular_feature,
        _ball_tool(),
        _operation(MotionMode.SIMULTANEOUS_4_PLUS_1),
        MachineProfile(),
    )
    cuts = _cuts(result.machine_path)

    assert len({round(point.c_deg, 9) for point in cuts}) == 1
    assert len({round(point.b_deg, 6) for point in cuts}) > 1


def test_5_axis_has_continuous_c(circular_feature):
    result = calculate_toolpath(
        circular_feature,
        _ball_tool(),
        _operation(MotionMode.SIMULTANEOUS_5_AXIS),
        MachineProfile(),
    )
    cuts = _cuts(result.machine_path)

    assert len({round(point.c_deg, 6) for point in cuts}) > 1
    assert max(
        abs(current.c_deg - previous.c_deg)
        for previous, current in zip(cuts, cuts[1:])
    ) <= 180.0


def test_ball_center_is_preserved_when_posture_is_realized(
    circular_feature,
):
    tool = _ball_tool()
    first = calculate_toolpath(
        circular_feature,
        tool,
        _operation(
            MotionMode.INDEXED_3_PLUS_2,
            auto_index=False,
            indexed_b_deg=0.0,
            indexed_c_deg=0.0,
        ),
        MachineProfile(),
    )
    second = calculate_toolpath(
        circular_feature,
        tool,
        _operation(
            MotionMode.INDEXED_3_PLUS_2,
            auto_index=False,
            indexed_b_deg=-45.0,
            indexed_c_deg=30.0,
        ),
        MachineProfile(),
    )
    radius = tool.diameter * 0.5
    first_cuts = _cuts(first.model_path)
    second_cuts = _cuts(second.model_path)

    for left, right in zip(first_cuts[:5], second_cuts[:5]):
        left_center = tuple(
            left.xyz[index] + left.tool_axis[index] * radius
            for index in range(3)
        )
        right_center = tuple(
            right.xyz[index] + right.tool_axis[index] * radius
            for index in range(3)
        )
        assert left_center == pytest.approx(right_center)
        assert left.xyz != right.xyz


def test_infeasible_indexed_chamfer_blocks_posting(circular_feature):
    rotated_samples = tuple(
        replace(
            sample,
            guide_normal=sample.other_normal,
            other_normal=(0.0, 0.0, 1.0),
        )
        for sample in circular_feature.samples
    )
    loop = replace(circular_feature, samples=rotated_samples)
    tool = ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=20.0,
        included_angle_deg=90.0,
        contact_radius=0.5,
    )

    with pytest.raises(ValidationError, match="station"):
        calculate_toolpath(
            loop,
            tool,
            Operation(
                id="blocked",
                tool_id=tool.id,
                target_width=0.5,
                motion_mode=MotionMode.INDEXED_3_PLUS_2,
            ),
            MachineProfile(),
        )


def test_preview_poses_match_machine_path_block_for_block(
    circular_feature,
):
    profile = MachineProfile()
    result = calculate_toolpath(
        circular_feature,
        _ball_tool(),
        _operation(MotionMode.SIMULTANEOUS_5_AXIS),
        profile,
    )
    preview = build_preview(
        circular_feature, result, tool=_ball_tool(), profile=profile
    )

    assert len(preview.tool_poses) == len(result.machine_path.points)
    for pose, machine in zip(
        preview.tool_poses, result.machine_path.points
    ):
        assert pose.b_deg == machine.b_deg
        assert pose.c_deg == machine.c_deg
        assert pose.motion is machine.motion
        assert pose.machine_xyz_radius == machine.xyz_radius
        assert pose.tool_axis == pytest.approx(
            axis_model_from_bc(
                machine.b_deg, machine.c_deg, profile
            )
        )


@pytest.mark.parametrize(
    "legacy,expected",
    [
        ("fixed", MotionMode.INDEXED_3_PLUS_2.value),
        ("simultaneous", MotionMode.SIMULTANEOUS_5_AXIS.value),
    ],
)
def test_legacy_axis_settings_migrate_to_explicit_modes(
    legacy, expected
):
    migrated = migrate_ui_settings({"c_axis_mode": legacy})

    assert migrated["motion_mode"] == expected
