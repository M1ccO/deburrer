from pathlib import Path

from fc_deburr.domain.models import (
    MachinePoint,
    MachineToolpath,
    MotionKind,
)
from fc_deburr.machine.post_ntx import NtxPostSettings, post_ntx_tcp
from fc_deburr.machine.profiles import MachineProfile


def test_ntx_minimal_program_matches_golden_file():
    path = MachineToolpath(
        feature_id="fixture",
        operation_id="fixture",
        tool_id="fixture",
        points=(
            MachinePoint(0, (34.0, 0.0, -41.0), -45.0, 0.0, MotionKind.RAPID),
            MachinePoint(
                1, (32.0, 2.0, -42.0), -50.0, 1.0, MotionKind.CUT, 800.0
            ),
            MachinePoint(2, (34.0, 0.0, -41.0), -45.0, 0.0, MotionKind.RETRACT),
        ),
    )
    actual = post_ntx_tcp(
        path,
        MachineProfile(),
        NtxPostSettings(program_number=9001, tool_code="T6456."),
    )
    expected = (
        Path(__file__).parent / "golden" / "ntx_minimal.nc"
    ).read_text(encoding="utf-8")

    assert actual == expected
