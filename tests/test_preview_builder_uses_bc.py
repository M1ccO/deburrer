import math

import pytest

from fc_deburr.machine.kinematics import (
    axis_machine_from_b,
    axis_model_from_bc,
    machine_to_model,
)
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.preview.builder import _machine_poses
from fc_deburr.application.pipeline import PipelineResult
from fc_deburr.domain.models import (
    MachinePoint,
    MachineToolpath,
    MotionKind,
    PathPoint,
    Toolpath,
)


def _synthetic_result(b_deg, c_deg):
    point = PathPoint(
        seq=0,
        xyz=(10.0, 20.0, 30.0),
        tool_axis=(0.0, 1.0, 0.0),
        motion=MotionKind.CUT,
    )
    machine = MachinePoint(
        seq=0,
        xyz_radius=(10.0, 20.0, 30.0),
        b_deg=b_deg,
        c_deg=c_deg,
        motion=MotionKind.CUT,
    )
    return PipelineResult(
        model_path=Toolpath(
            feature_id="f1",
            operation_id="op1",
            tool_id="t1",
            points=(point,),
        ),
        machine_path=MachineToolpath(
            feature_id="f1",
            operation_id="op1",
            tool_id="t1",
            points=(machine,),
        ),
        validation=object(),
    )


def test_tool_axis_includes_c_rotation():
    profile = MachineProfile()
    result = _synthetic_result(b_deg=-30.0, c_deg=90.0)
    poses = _machine_poses(result, profile)
    pose = poses[0]

    expected = axis_model_from_bc(-30.0, 90.0, profile)
    assert pose.tool_axis == pytest.approx(expected)

    without_c = axis_model_from_bc(-30.0, 0.0, profile)
    assert pose.tool_axis != pytest.approx(without_c)

    expected_b_only = machine_to_model(
        axis_machine_from_b(-30.0, profile), profile
    )
    assert pose.tool_axis_b_only == pytest.approx(expected_b_only)


def test_tool_axis_zero_c_matches_pure_b():
    profile = MachineProfile()
    result = _synthetic_result(b_deg=0.0, c_deg=0.0)
    poses = _machine_poses(result, profile)
    pose = poses[0]

    expected = axis_model_from_bc(0.0, 0.0, profile)
    assert pose.tool_axis == pytest.approx(expected)


def test_part_rotation_matches_physical_c():
    profile = MachineProfile()
    result = _synthetic_result(b_deg=0.0, c_deg=45.0)
    poses = _machine_poses(result, profile)
    pose = poses[0]

    physical_c = (
        45.0 - profile.c_zero_offset_deg
    ) / profile.c_axis_sign
    assert pose.part_rotation_deg == pytest.approx(physical_c)


def test_multiple_points_each_get_correct_axes():
    profile = MachineProfile(c_axis_sign=-1.0)
    points = tuple(
        PathPoint(
            seq=i,
            xyz=(float(i), 0.0, 0.0),
            tool_axis=(0.0, 1.0, 0.0),
            motion=MotionKind.CUT,
        )
        for i in range(3)
    )
    machines = tuple(
        MachinePoint(
            seq=i,
            xyz_radius=(float(i), 0.0, 0.0),
            b_deg=float(-30 + 10 * i),
            c_deg=float(90 + 30 * i),
            motion=MotionKind.CUT,
        )
        for i in range(3)
    )
    result = PipelineResult(
        model_path=Toolpath(
            feature_id="f1", operation_id="op1", tool_id="t1",
            points=points,
        ),
        machine_path=MachineToolpath(
            feature_id="f1", operation_id="op1", tool_id="t1",
            points=machines,
        ),
        validation=object(),
    )
    poses = _machine_poses(result, profile)
    for i, (pose, machine) in enumerate(zip(poses, machines)):
        expected = axis_model_from_bc(
            machine.b_deg, machine.c_deg, profile
        )
        assert pose.tool_axis == pytest.approx(expected)
        physical_c = (
            machine.c_deg - profile.c_zero_offset_deg
        ) / profile.c_axis_sign
        assert pose.part_rotation_deg == pytest.approx(physical_c)
