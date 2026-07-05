from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.domain.models import (
    FeatureSourceKind,
    MotionKind,
    MotionMode,
    Operation,
    PositioningMode,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.domain.serialization import load_feature
from fc_deburr.machine.profiles import MachineProfile


def _summary(values, label):
    if not values:
        return f"  {label}: (empty)"
    return (
        f"  {label}: min={min(values):.3f}  max={max(values):.3f}  "
        f"mean={sum(values)/len(values):.3f}  span={max(values)-min(values):.3f}"
    )


def _format_vector(v):
    return f"({v[0]:+.4f}, {v[1]:+.4f}, {v[2]:+.4f})"


def main():
    feature_path = Path(__file__).resolve().parent.parent / "deburr_feature.json"
    if len(sys.argv) > 1:
        feature_path = Path(sys.argv[1])
    if not feature_path.exists():
        print(f"ERROR: feature file not found: {feature_path}")
        sys.exit(1)

    print(f"=== 5-Axis C-Axis Diagnostic ===")
    print(f"Feature file: {feature_path}")
    print()

    feature = load_feature(feature_path)
    print(f"Feature: id={feature.id}  source={feature.source_object_id}")
    print(f"  closed={feature.closed}  samples={len(feature.samples)}")
    print(f"  center_xyz={feature.center_xyz}")
    print(f"  source_kind={feature.source_kind}")
    print()

    tool = ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=25.0,
        cutting_length=0.0,
        contact_radius=0.5,
    )
    operation = Operation(
        id="diag",
        tool_id=tool.id,
        target_width=0.5,
        ball_engagement=0.25,
        feed=800.0,
        lead_deg=0.0,
        tilt_deg=0.0,
        lead_in_length=2.0,
        lead_out_length=2.0,
        safety_lift=3.0,
        positioning_mode=PositioningMode.TANGENT,
        flip_side=False,
        motion_mode=MotionMode.SIMULTANEOUS_5_AXIS,
        auto_index=True,
    )
    profile = MachineProfile()

    print("Running pipeline in SIMULTANEOUS_5_AXIS mode...")
    try:
        result = calculate_toolpath(feature, tool, operation, profile)
    except Exception as exc:
        print(f"PIPELINE FAILED: {exc}")
        sys.exit(2)

    print(f"  ok=True  cut_points={len(result.model_path.points)}")
    print(f"  indexed_b={result.indexed_b_deg}  indexed_c={result.indexed_c_deg}")
    print(f"  side_auto_picked={result.side_auto_picked}  side_used={result.side_used}")
    print()

    machine = result.machine_path
    cut_machines = [p for p in machine.points if str(p.motion) == "MotionKind.CUT"]
    print(f"Machine path: {len(machine.points)} total, {len(cut_machines)} CUT")
    print()

    b_vals = [p.b_deg for p in machine.points]
    c_vals = [p.c_deg for p in machine.points]
    print("--- Axis ranges (all points) ---")
    print(_summary(b_vals, "B"))
    print(_summary(c_vals, "C"))
    print()

    b_cuts = [p.b_deg for p in cut_machines]
    c_cuts = [p.c_deg for p in cut_machines]
    print("--- Axis ranges (CUT only) ---")
    print(_summary(b_cuts, "B"))
    print(_summary(c_cuts, "C"))
    print()

    cut_models = [p for p in result.model_path.points if str(p.motion) == "MotionKind.CUT"]
    tool_axes = [p.tool_axis for p in cut_models]
    print("--- Tool axis (model frame, CUT only) ---")
    if tool_axes:
        print(f"  first:  {_format_vector(tool_axes[0])}")
        print(f"  last:   {_format_vector(tool_axes[-1])}")
        print(f"  middle: {_format_vector(tool_axes[len(tool_axes)//2])}")
    print()

    print("--- First 10 CUT points ---")
    print(f"  {'i':>4}  {'B':>8}  {'C':>8}  tool_axis")
    for i, p in enumerate(cut_machines[:10]):
        axis = tool_axes[i] if i < len(tool_axes) else (0, 0, 0)
        print(f"  {i:>4}  {p.b_deg:>8.3f}  {p.c_deg:>8.3f}  {_format_vector(axis)}")
    print()

    print("--- Last 10 CUT points ---")
    print(f"  {'i':>4}  {'B':>8}  {'C':>8}  tool_axis")
    start = max(0, len(cut_machines) - 10)
    for j, p in enumerate(cut_machines[start:]):
        i = start + j
        axis = tool_axes[i] if i < len(tool_axes) else (0, 0, 0)
        print(f"  {i:>4}  {p.b_deg:>8.3f}  {p.c_deg:>8.3f}  {_format_vector(axis)}")
    print()

    print("--- Assertions ---")
    ok = True
    if len(c_cuts) < 2:
        print("  WARN: fewer than 2 CUT points")
    else:
        c_span = max(c_cuts) - min(c_cuts)
        if c_span < 1e-3:
            print(f"  FAIL: C-axis does not vary (span={c_span:.6f})")
            ok = False
        else:
            print(f"  PASS: C-axis varies (span={c_span:.3f} deg)")

    b_span = max(b_cuts) - min(b_cuts)
    if b_span < 1e-3:
        print(f"  WARN: B-axis does not vary (span={b_span:.6f}) — may be intentional")
    else:
        print(f"  PASS: B-axis varies (span={b_span:.3f} deg)")

    if result.machine_path.warnings:
        print()
        print("--- Solver warnings ---")
        for w in result.machine_path.warnings:
            print(f"  - {w}")

    if not ok:
        print()
        print("OVERALL: FAIL — C-axis not working correctly in 5-axis mode")
        sys.exit(3)
    print()
    print("OVERALL: PASS — C-axis is working in 5-axis mode")


if __name__ == "__main__":
    main()
