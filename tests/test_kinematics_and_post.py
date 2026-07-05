import pytest

from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.domain.models import MotionKind, Operation, ToolDefinition, ToolKind
from fc_deburr.machine.post_ntx import NtxPostSettings, post_ntx_tcp
from fc_deburr.machine.profiles import MachineProfile


def _result(circular_feature):
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
        lead_in_length=1.0,
        lead_out_length=1.0,
        safety_lift=2.0,
    )
    profile = MachineProfile()
    return calculate_toolpath(circular_feature, tool, operation, profile), profile


def test_machine_path_has_separate_radius_coordinates_and_c0(circular_feature):
    result, _ = _result(circular_feature)
    first_cut = next(
        point for point in result.machine_path.points
        if point.motion is MotionKind.CUT
    )

    assert first_cut.c_deg == pytest.approx(0.0, abs=1.0e-12)
    assert first_cut.xyz_radius[0] == result.model_path.points[2].xyz[2]
    assert first_cut.xyz_radius[1] == result.model_path.points[2].xyz[1]
    assert first_cut.xyz_radius[2] == result.model_path.points[2].xyz[0]


def test_ntx_post_uses_tcp_wrapper_and_diameter_x(circular_feature):
    result, profile = _result(circular_feature)
    settings = NtxPostSettings(
        program_number=9001,
        tool_code="T6456.",
        spindle_speed=6000,
        spindle_direction="M03",
        coolant_on=True,
    )

    nc = post_ntx_tcp(result.machine_path, profile, settings)

    assert "G43.4 D9" in nc
    assert "CALIBRATION REQUIRED" in nc
    assert "M594 (B-AXIS CONTOUR ON)" in nc
    assert "(--------------------------)" in nc
    assert "M595 (B-AXIS CONT. OFF)" in nc
    assert "M46 (C-AXIS OFF)" in nc
    assert "S6000 M03" in nc
    assert "M08" in nc
    first = result.machine_path.points[0]
    expected_x = "X%s" % (
        ("%.4f" % (first.xyz_radius[0] * 2.0)).rstrip("0").rstrip(".")
    )
    assert expected_x in nc
    assert "(RAPID)" in nc
    assert "(CUT)" in nc
