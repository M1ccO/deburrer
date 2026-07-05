import json

from fc_deburr.application.session import DeburrSession
from fc_deburr.domain.models import (
    MotionKind,
    Operation,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.domain.serialization import feature_loop_to_document
from fc_deburr.machine.post_ntx import NtxPostSettings
from fc_deburr.machine.profiles import MachineProfile


def test_session_replaces_derived_data_when_feature_loads(
    circular_feature, tmp_path
):
    path = tmp_path / "feature.json"
    path.write_text(
        json.dumps(feature_loop_to_document(circular_feature)),
        encoding="utf-8",
    )
    session = DeburrSession()
    session.load_feature(path)
    tool = ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=20.0,
        included_angle_deg=90.0,
        contact_radius=0.5,
    )
    operation = Operation(
        id="op", tool_id=tool.id, target_width=0.5
    )
    profile = MachineProfile()

    session.calculate(tool, operation, profile)
    nc = session.post(
        profile, NtxPostSettings(program_number=9001, tool_code="T6456.")
    )

    assert session.preview is not None
    assert len(session.preview.polylines) == 7
    assert session.preview.markers[0].name == "C0 / start"
    assert session.preview.tool.kind == "chamfer"
    assert session.preview.tool.diameter == 6.0
    assert session.preview.tool.stickout == 20.0
    assert session.preview.tool.included_angle_deg == 90.0
    assert len(session.preview.tool_poses) == len(
        session.result.machine_path.points
    )
    assert (
        session.preview.tool_poses[0].b_deg
        == session.result.machine_path.points[0].b_deg
    )
    assert "G43.4 D9" in nc
    session.load_feature(path)
    assert session.result is None
    assert session.preview is None
    assert session.nc_text is None
