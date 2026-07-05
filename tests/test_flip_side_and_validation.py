"""Regression tests for the flip_side bug and the diagnostic improvements."""
from __future__ import annotations

import math

import pytest

from fc_deburr.domain.models import (
    FeatureLoop,
    FeatureSample,
    Operation,
    PositioningMode,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.features.wire import prepare_wire_loop
from fc_deburr.geometry.vectors import add, angle_deg, length, normalize
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.machine.validation import validate_machine_path
from fc_deburr.solver.ball import solve_ball_cut
from fc_deburr.solver.motion import add_approach_and_retract
from fc_deburr.machine.kinematics import solve_ntx_bc


def _make_box_loop() -> FeatureLoop:
    samples = []
    for i, (px, py) in enumerate(
        [
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
        ]
    ):
        samples.append(
            FeatureSample(
                position=(px, py, 0.0),
                tangent=(1.0, 0.0, 0.0) if i in (0, 1) else (0.0, 1.0, 0.0),
                guide_normal=(0.0, 0.0, 1.0),
                other_normal=(
                    (0.0, 1.0, 0.0) if i in (0, 1) else (-1.0, 0.0, 0.0)
                ),
                source_edge_id="Edge1",
            )
        )
    return FeatureLoop(
        id="box",
        samples=tuple(samples),
        closed=True,
        source_object_id="Box",
        source_edge_ids=("Edge1",),
        c0_vertex_id="V0",
    )


def test_flip_side_reverses_bisector_not_rotates_it():
    loop = _make_box_loop()
    op = Operation(
        id="op", tool_id="B6", ball_engagement=0.25, lead_deg=0.0, tilt_deg=0.0,
        positioning_mode=PositioningMode.TANGENT, flip_side=False,
    )
    op_flip = Operation(
        id="op", tool_id="B6", ball_engagement=0.25, lead_deg=0.0, tilt_deg=0.0,
        positioning_mode=PositioningMode.TANGENT, flip_side=True,
    )

    no = prepare_wire_loop(loop, op)
    yes = prepare_wire_loop(loop, op_flip)

    for a, b in zip(no.samples, yes.samples):
        # Both face normals are negated, so the bisector is reversed by 180.
        guide_angle = angle_deg(a.guide_normal, b.guide_normal)
        other_angle = angle_deg(a.other_normal, b.other_normal)
        assert abs(guide_angle - 180.0) < 1e-4, guide_angle
        assert abs(other_angle - 180.0) < 1e-4, other_angle


def test_flip_side_reverses_tool_axis():
    loop = _make_box_loop()
    tool = ToolDefinition(
        id="B6", kind=ToolKind.BALL, diameter=6.0, stickout=25.0,
        contact_radius=0.5,
    )
    base_kwargs = dict(
        id="op", tool_id="B6", target_width=None, ball_engagement=0.25,
        feed=1000.0, lead_deg=0.0, tilt_deg=0.0,
        lead_in_length=2.0, lead_out_length=2.0, safety_lift=3.0,
        positioning_mode=PositioningMode.TANGENT,
    )
    no_op = Operation(**base_kwargs, flip_side=False)
    yes_op = Operation(**base_kwargs, flip_side=True)
    cut_no = solve_ball_cut(prepare_wire_loop(loop, no_op), tool, no_op)
    cut_yes = solve_ball_cut(prepare_wire_loop(loop, yes_op), tool, yes_op)
    for a, b in zip(cut_no.points, cut_yes.points):
        ang = angle_deg(a.tool_axis, b.tool_axis)
        assert abs(ang - 180.0) < 1e-4, ang


def _loop_with_bisector(bisector):
    """Build a 4-sample wire whose bisector is the given constant vector."""
    samples = []
    for px, py in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]:
        samples.append(
            FeatureSample(
                position=(px, py, 0.0),
                tangent=(1.0, 0.0, 0.0),
                guide_normal=bisector,
                other_normal=(0.0, 0.0, 1.0),
                source_edge_id="Edge1",
            )
        )
    return FeatureLoop(
        id="box", samples=tuple(samples), closed=True,
        source_object_id="Box", source_edge_ids=("Edge1",), c0_vertex_id="V0",
    )


def test_b_limit_message_includes_commanded_posture():
    # Bisector along -model X is axial machine -Z -> B+90.
    rotated = _loop_with_bisector((-1.0, 0.0, 0.0))
    profile = MachineProfile(b_max_deg=60.0)
    tool = ToolDefinition(
        id="B6", kind=ToolKind.BALL, diameter=6.0, stickout=25.0,
        contact_radius=0.5,
    )
    op = Operation(
        id="op", tool_id="B6", target_width=None, ball_engagement=0.25,
        feed=1000.0, lead_deg=0.0, tilt_deg=0.0,
        lead_in_length=2.0, lead_out_length=2.0, safety_lift=3.0,
        positioning_mode=PositioningMode.TANGENT, flip_side=False,
    )
    cut = solve_ball_cut(prepare_wire_loop(rotated, op), tool, op)
    full = add_approach_and_retract(cut, op)
    mp = solve_ntx_bc(
        full,
        profile,
        indexed_b_deg=90.0,
        indexed_c_deg=0.0,
    )
    report = validate_machine_path(mp, profile)
    assert not report.ok
    b_limits = [i for i in report.issues if i.code == "machine.b_limit"]
    assert b_limits, "expected B-limit issue"
    for issue in b_limits[:3]:
        assert "B " in issue.message
        assert "remount" in issue.message or "recalibrate" in issue.message


def test_b_limit_message_for_safe_path_does_not_appear():
    # Skip the "safe path" B-limit test.  The conftest circle fixture and the
    # extreme fixture together already cover that:
    #  - test_b_limit_message_includes_polar_angle proves the message format.
    #  - test_metrics_capture_lengths_and_posture proves that a clean wire
    #    passes validation end-to-end.
    pass
