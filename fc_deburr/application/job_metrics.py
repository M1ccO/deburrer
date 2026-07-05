"""CAM-style job summary statistics.

Owns nothing mutable.  Given a validated machine path and its feature, returns
metrics the UI renders in the status panel: cut length, cycle estimate, B/C
posture range, bisector polar range, cutter contact extents, and warnings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple

from ..domain.models import (
    FeatureLoop,
    MachinePoint,
    MachineToolpath,
    MotionKind,
)
from ..geometry.vectors import add, length, normalize, scale, sub
from ..machine.kinematics import model_to_machine
from ..machine.profiles import MachineProfile


@dataclass(frozen=True)
class JobMetrics:
    """Immutable summary a CAM UI can show without recomputing the path."""

    point_count: int
    cut_point_count: int
    rapid_point_count: int
    cut_length_mm: float
    rapid_length_mm: float
    total_length_mm: float
    cycle_time_min: float
    feed_mm_per_min: float
    b_min: float
    b_max: float
    c_min: float
    c_max: float
    bisector_polar_min_deg: float
    bisector_polar_max_deg: float
    contact_extent_min_mm: float
    contact_extent_max_mm: float
    safe_z_mm: float
    closed: bool
    warnings: Tuple[str, ...] = ()


def _distances(points: Iterable[MachinePoint]) -> Tuple[float, float]:
    cut = 0.0
    rapid = 0.0
    previous = None
    for point in points:
        if previous is not None:
            segment = length(sub(point.xyz_radius, previous.xyz_radius))
            if point.motion in (MotionKind.RAPID, MotionKind.RETRACT):
                rapid += segment
            else:
                cut += segment
        previous = point
    return cut, rapid


def _safe_z(path: MachineToolpath) -> float:
    zs = [p.xyz_radius[2] for p in path.points]
    return max(zs) if zs else 0.0


def _bisector_polar_range(
    feature: FeatureLoop, profile: MachineProfile
) -> Tuple[float, float]:
    """Polar range of the source bisector after the model->machine transform.

    This reflects the user-requested side (``flip_side``) on the feature as
    loaded, *not* the side the engine may have auto-picked.  Use
    :func:`_actual_tool_polar_range` for the polar range of the toolpath that
    actually got posted.
    """
    if not feature.samples:
        return 0.0, 0.0
    polars = []
    for sample in feature.samples:
        bisector = add(sample.guide_normal, sample.other_normal)
        if length(bisector) <= 1.0e-9:
            continue
        machine_axis = model_to_machine(normalize(bisector), profile)
        polar = math.degrees(
            math.acos(max(-1.0, min(1.0, machine_axis[2])))
        )
        polars.append(polar)
    if not polars:
        return 0.0, 0.0
    return min(polars), max(polars)


def _actual_tool_polar_range(
    path, profile: MachineProfile
) -> Tuple[float, float]:
    """Polar range of the tool axes that actually got posted."""
    polars: list[float] = []
    for point in path.points:
        if point.tool_axis is None:
            continue
        machine_axis = model_to_machine(
            normalize(tuple(point.tool_axis)), profile
        )
        polar = math.degrees(
            math.acos(max(-1.0, min(1.0, machine_axis[2])))
        )
        polars.append(polar)
    if not polars:
        return 0.0, 0.0
    return min(polars), max(polars)


def _contact_extents(
    feature: FeatureLoop, profile: MachineProfile
) -> Tuple[float, float]:
    if not feature.samples or feature.center_xyz is None:
        return 0.0, 0.0
    center = feature.center_xyz
    rs = []
    for sample in feature.samples:
        d = length(sub(sample.position, center))
        rs.append(d)
    return min(rs), max(rs)


def estimate_job(
    feature: FeatureLoop,
    path: MachineToolpath,
    profile: MachineProfile,
    feed_mm_per_min: Optional[float] = None,
    safe_rapid_mm_per_min: float = 8000.0,
    model_path: Optional["Toolpath"] = None,
) -> JobMetrics:
    """Return CAM-style job metrics for the UI status panel.

    ``feed_mm_per_min`` defaults to the feed declared by the first CUT point.
    ``model_path`` (when provided) is used for the *actual* tool-axis polar
    range, which reflects the side the engine actually posted.  When omitted,
    the polar range is computed from the source feature bisector, which may
    not match if the pipeline auto-picked the opposite side.
    """

    cut, rapid = _distances(path.points)
    feed = feed_mm_per_min
    if feed is None or feed <= 0.0:
        for point in path.points:
            if point.motion is MotionKind.CUT and point.feed:
                feed = float(point.feed)
                break
    if feed is None or feed <= 0.0:
        feed = 800.0

    rapid_min = rapid / max(1.0, safe_rapid_mm_per_min)
    cut_min = cut / max(1.0, feed)
    cycle_min = rapid_min + cut_min

    bs = [p.b_deg for p in path.points]
    cs = [p.c_deg for p in path.points]
    if model_path is not None:
        polar_min, polar_max = _actual_tool_polar_range(model_path, profile)
    else:
        polar_min, polar_max = _bisector_polar_range(feature, profile)
    contact_min, contact_max = _contact_extents(feature, profile)

    warnings: list[str] = []
    if abs(polar_max) > 120.0 or abs(polar_min) > 120.0:
        warnings.append(
            "Tool axis exceeds the B-axis envelope "
            "(polar %.1f..%.1f deg). Re-mount the part or recalibrate "
            "the model-to-machine mapping." % (polar_min, polar_max)
        )
    if path.warnings:
        warnings.extend(path.warnings)

    return JobMetrics(
        point_count=len(path.points),
        cut_point_count=sum(
            1 for p in path.points if p.motion is MotionKind.CUT
        ),
        rapid_point_count=sum(
            1
            for p in path.points
            if p.motion in (MotionKind.RAPID, MotionKind.RETRACT)
        ),
        cut_length_mm=cut,
        rapid_length_mm=rapid,
        total_length_mm=cut + rapid,
        cycle_time_min=cycle_min,
        feed_mm_per_min=feed,
        b_min=min(bs) if bs else 0.0,
        b_max=max(bs) if bs else 0.0,
        c_min=min(cs) if cs else 0.0,
        c_max=max(cs) if cs else 0.0,
        bisector_polar_min_deg=polar_min,
        bisector_polar_max_deg=polar_max,
        contact_extent_min_mm=contact_min,
        contact_extent_max_mm=contact_max,
        safe_z_mm=_safe_z(path),
        closed=getattr(feature, "closed", False),
        warnings=tuple(warnings),
    )


def format_metrics(metrics: JobMetrics, profile: Optional[MachineProfile] = None) -> str:
    """Render a multi-line CAM-style status block for the UI text view."""

    if profile is not None:
        profile_line = (
            "MACHINE PROFILE: %s (%s)"
            % (
                profile.id,
                "verified" if profile.calibrated else "calibration REQUIRED",
            )
        )
    else:
        profile_line = "MACHINE PROFILE: <not supplied>"
    lines = [
        "GEOMETRY VALIDATED",
        profile_line,
        "",
        "Path",
        "  points        : %d  (cut %d, rapid %d)"
        % (
            metrics.point_count,
            metrics.cut_point_count,
            metrics.rapid_point_count,
        ),
        "  cut length    : %.2f mm" % metrics.cut_length_mm,
        "  rapid length  : %.2f mm" % metrics.rapid_length_mm,
        "  total length  : %.2f mm" % metrics.total_length_mm,
        "  feed          : %.0f mm/min" % metrics.feed_mm_per_min,
        "  cycle est.    : %.2f min" % metrics.cycle_time_min,
        "",
        "Posture",
        "  B range       : %.3f .. %.3f deg" % (metrics.b_min, metrics.b_max),
        "  C range       : %.3f .. %.3f deg" % (metrics.c_min, metrics.c_max),
        "  bisector polar: %.2f .. %.2f deg (limit 120 deg)"
        % (metrics.bisector_polar_min_deg, metrics.bisector_polar_max_deg),
        "  safe Z        : %.3f mm" % metrics.safe_z_mm,
        "",
        "Geometry",
        "  contact extent: %.3f .. %.3f mm from wire center"
        % (metrics.contact_extent_min_mm, metrics.contact_extent_max_mm),
        "  closed loop   : %s" % ("yes" if metrics.closed else "no"),
    ]
    if metrics.warnings:
        lines.append("")
        lines.append("Notes")
        for note in metrics.warnings:
            lines.append("  - " + note)
    return "\n".join(lines)
