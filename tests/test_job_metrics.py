"""Tests for the CAM-style job metrics module."""
from __future__ import annotations

import math

from fc_deburr.application.job_metrics import estimate_job, format_metrics
from fc_deburr.domain.models import (
    FeatureLoop,
    FeatureSample,
    Operation,
    PositioningMode,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.features.wire import prepare_wire_loop
from fc_deburr.machine.kinematics import solve_ntx_bc
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.solver.ball import solve_ball_cut
from fc_deburr.solver.motion import add_approach_and_retract


def _solve(feature):
    profile = MachineProfile()
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
    cut = solve_ball_cut(prepare_wire_loop(feature, op), tool, op)
    full = add_approach_and_retract(cut, op)
    mp = solve_ntx_bc(full, profile)
    return feature, mp, profile


def _safe_circle():
    # Bisector along +Z (machine X) -> polar=0 -> safely inside the B range.
    samples = []
    for i in range(24):
        a = 2.0 * math.pi * i / 24.0
        samples.append(
            FeatureSample(
                position=(10.0 * math.cos(a), 10.0 * math.sin(a), 0.0),
                tangent=(-math.sin(a), math.cos(a), 0.0),
                guide_normal=(0.0, 0.0, 1.0),
                other_normal=(math.cos(a), math.sin(a), 0.0),
                source_edge_id="Edge1",
            )
        )
    return FeatureLoop(
        id="circle", samples=tuple(samples), closed=True,
        source_object_id="Test", c0_vertex_id="V0",
    )


def test_metrics_capture_lengths_and_posture():
    feature = _safe_circle()
    feature, mp, profile = _solve(feature)
    metrics = estimate_job(feature, mp, profile)

    assert metrics.point_count == len(mp.points)
    assert metrics.cut_point_count > 0
    assert metrics.rapid_point_count > 0
    assert metrics.cut_length_mm > 0.0
    assert metrics.rapid_length_mm >= 0.0
    assert metrics.total_length_mm == (
        metrics.cut_length_mm + metrics.rapid_length_mm
    )
    assert metrics.b_min <= metrics.b_max
    assert metrics.c_min <= metrics.c_max
    assert metrics.feed_mm_per_min > 0.0
    assert metrics.cycle_time_min > 0.0
    assert metrics.closed is True


def test_metrics_warn_when_bisector_polar_exceeds_limit():
    # Bisector pointing along -X (machine Z) -> polar=180 -> exceeds the limit.
    samples = []
    for px, py in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]:
        samples.append(
            FeatureSample(
                position=(px, py, 0.0),
                tangent=(1.0, 0.0, 0.0),
                guide_normal=(-1.0, 0.0, 0.0),
                other_normal=(0.0, 0.0, 1.0),
                source_edge_id="Edge1",
            )
        )
    loop = FeatureLoop(
        id="extreme", samples=tuple(samples), closed=True,
        source_object_id="Test",
    )
    profile = MachineProfile()
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
    cut = solve_ball_cut(prepare_wire_loop(loop, op), tool, op)
    full = add_approach_and_retract(cut, op)
    mp = solve_ntx_bc(full, profile)
    metrics = estimate_job(loop, mp, profile)
    assert any("bisector" in w.lower() or "tool axis" in w.lower() for w in metrics.warnings)


def test_format_metrics_returns_text():
    feature = _safe_circle()
    profile = MachineProfile()
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
    cut = solve_ball_cut(prepare_wire_loop(feature, op), tool, op)
    full = add_approach_and_retract(cut, op)
    mp = solve_ntx_bc(full, profile)
    metrics = estimate_job(feature, mp, profile)
    text = format_metrics(metrics)
    assert "GEOMETRY VALIDATED" in text
    assert "B range" in text
    assert "cut length" in text
    assert "cycle est." in text
