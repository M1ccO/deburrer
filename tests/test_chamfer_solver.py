import pytest

from fc_deburr.domain.errors import GeometryError
from fc_deburr.domain.models import Operation, ToolDefinition, ToolKind
from fc_deburr.solver.chamfer import solve_chamfer_cut


def chamfer_tool():
    return ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=25.0,
        included_angle_deg=90.0,
        tip_flat_diameter=0.0,
        contact_radius=0.5,
    )


def test_chamfer_width_changes_cutter_path_not_source(circular_feature):
    original = circular_feature
    narrow = solve_chamfer_cut(
        circular_feature,
        chamfer_tool(),
        Operation(id="narrow", tool_id="C90", target_width=0.5),
    )
    wide = solve_chamfer_cut(
        circular_feature,
        chamfer_tool(),
        Operation(id="wide", tool_id="C90", target_width=1.0),
    )

    assert circular_feature is original
    assert circular_feature.samples[0].position == (10.0, 0.0, 0.0)
    assert narrow.points[0].contact_xyz == pytest.approx((9.75, 0.0, -0.25))
    assert wide.points[0].contact_xyz == pytest.approx((9.5, 0.0, -0.5))
    assert narrow.points[0].target_a_xyz == pytest.approx((9.5, 0.0, 0.0))
    assert narrow.points[0].target_b_xyz == pytest.approx((10.0, 0.0, -0.5))
    assert narrow.points[0].xyz != wide.points[0].xyz
    assert narrow.points[-1].xyz == narrow.points[0].xyz
    assert "closure" in narrow.points[-1].flags


def test_chamfer_tilt_is_rejected_because_it_changes_flat_geometry(
    circular_feature,
):
    with pytest.raises(GeometryError, match="tilt changes"):
        solve_chamfer_cut(
            circular_feature,
            chamfer_tool(),
            Operation(
                id="tilted",
                tool_id="C90",
                target_width=0.5,
                tilt_deg=2.0,
            ),
        )


def test_chamfer_requires_explicit_contact_radius(circular_feature):
    tool = ToolDefinition(
        id="missing",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=20.0,
        included_angle_deg=90.0,
    )
    with pytest.raises(GeometryError, match="contact radius"):
        solve_chamfer_cut(
            circular_feature,
            tool,
            Operation(id="op", tool_id=tool.id, target_width=0.5),
        )
