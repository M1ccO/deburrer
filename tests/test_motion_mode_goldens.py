from pathlib import Path

import pytest

from fc_deburr.domain.models import (
    MotionKind,
    MotionMode,
    PathPoint,
    Toolpath,
)
from fc_deburr.machine.kinematics import (
    axis_model_from_bc,
    solve_ntx_bc,
)
from fc_deburr.machine.post_ntx import NtxPostSettings, post_ntx_tcp
from fc_deburr.machine.profiles import MachineProfile


GOLDEN = Path(__file__).parent / "golden"


def _path(axes):
    motions = (
        MotionKind.RAPID,
        MotionKind.CUT,
        MotionKind.RETRACT,
    )
    return Toolpath(
        feature_id="golden",
        operation_id="golden",
        tool_id="T100",
        points=tuple(
            PathPoint(
                seq=index,
                xyz=(10.0 + index, 2.0 * index, 3.0 * index),
                tool_axis=axis,
                motion=motions[index],
                feed=500.0 if index == 1 else None,
            )
            for index, axis in enumerate(axes)
        ),
    )


@pytest.mark.parametrize(
    "name,mode,bc,indexed_b,indexed_c",
    [
        (
            "ntx_3plus2.nc",
            MotionMode.INDEXED_3_PLUS_2,
            ((0.0, 0.0),) * 3,
            -45.0,
            30.0,
        ),
        (
            "ntx_4plus1.nc",
            MotionMode.SIMULTANEOUS_4_PLUS_1,
            ((0.0, 30.0), (-30.0, 30.0), (-60.0, 30.0)),
            None,
            30.0,
        ),
        (
            "ntx_5axis.nc",
            MotionMode.SIMULTANEOUS_5_AXIS,
            ((0.0, 0.0), (-30.0, 45.0), (-60.0, 90.0)),
            None,
            None,
        ),
    ],
)
def test_motion_mode_program_matches_golden(
    name, mode, bc, indexed_b, indexed_c
):
    profile = MachineProfile(
        b_min_deg=-180.0,
        b_max_deg=180.0,
        max_b_step_deg=60.0,
        max_c_step_deg=60.0,
    )
    axes = [
        axis_model_from_bc(b_deg, c_deg, profile)
        for b_deg, c_deg in bc
    ]
    machine = solve_ntx_bc(
        _path(axes),
        profile,
        motion_mode=mode,
        indexed_b_deg=indexed_b,
        indexed_c_deg=indexed_c,
    )
    nc = post_ntx_tcp(
        machine,
        profile,
        NtxPostSettings(program_number=9100, tool_code="T100."),
    )

    assert nc == (GOLDEN / name).read_text(encoding="utf-8")
