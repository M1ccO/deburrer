"""Standalone deburring pipeline — wires geometry extraction, contact solving,
posture realization, and kinematics into a complete machinable toolpath.

No dependency on fc_deburr.  Accepts sampled edge points from any geometry
source (OCCT, FreeCAD, mesh) and returns model-space + machine-space paths.

Machining strategies:
  - **ball_break**: Ball endmill rolling along edge with specified break width
  - **chamfer**: Chamfer mill with equal-face-width flat bevel
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from ..contact.solver_core import (
    SolverPoint,
    solve_ball_cut,
    solve_chamfer_cut,
    BallSolverError,
    ChamferSolverError,
)
from ..kinematics.kinematics_core import (
    MachinePoint,
    MachineToolpath,
    MotionMode,
    NtxConfig,
    NTX_DEFAULT,
    axis_model_from_bc,
    bc_from_axis_model,
    b_for_fixed_c_axis,
    machine_to_model,
    model_to_machine,
    solve_ntx_toolpath,
    workpiece_to_machine,
)

Vec3 = Tuple[float, float, float]

EPS = 1e-10


# ---------------------------------------------------------------------------
# Strategy enums
# ---------------------------------------------------------------------------

class ToolKind(str, Enum):
    BALL = "ball"
    CHAMFER = "chamfer"


class MotionKind(str, Enum):
    RAPID = "rapid"
    APPROACH = "approach"
    CUT = "cut"
    LEAD_OUT = "lead_out"
    RETRACT = "retract"


# ---------------------------------------------------------------------------
# Tool / operation descriptors (self-contained, no fc_deburr dependency)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolParams:
    kind: ToolKind
    diameter: float
    stickout: float = 40.0
    included_angle_deg: Optional[float] = None
    tip_flat_diameter: float = 0.0
    tip_radius: float = 0.0
    contact_radius: Optional[float] = None
    cutting_length: float = 12.0
    radial_correction: float = 0.0
    axial_correction: float = 0.0

    @property
    def radius(self) -> float:
        return self.diameter * 0.5


@dataclass(frozen=True)
class OperationParams:
    tool_id: str = ""
    target_width: Optional[float] = None
    ball_break_width: Optional[float] = None
    ball_engagement: Optional[float] = None
    feed: float = 800.0
    lead_deg: float = 0.0
    tilt_deg: float = 0.0
    lead_in_length: float = 2.0
    lead_out_length: float = 2.0
    safety_lift: float = 3.0
    flip_side: bool = False
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2
    auto_index: bool = True
    indexed_b_deg: Optional[float] = None
    indexed_c_deg: Optional[float] = None
    spring_passes: int = 0
    spring_feed_fraction: float = 0.5


# ---------------------------------------------------------------------------
# Path point types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PathPoint:
    seq: int
    xyz: Vec3
    tool_axis: Vec3
    motion: MotionKind
    contact_xyz: Optional[Vec3] = None
    tangent: Optional[Vec3] = None
    feed: Optional[float] = None
    flags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Toolpath:
    points: Tuple[PathPoint, ...]
    feature_id: str = ""
    tool_id: str = ""
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeburrResult:
    model_path: Toolpath
    machine_path: MachineToolpath
    indexed_b_deg: Optional[float] = None
    indexed_c_deg: Optional[float] = None
    warnings: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_deburr_pipeline(
    samples: Sequence,
    tool: ToolParams,
    operation: OperationParams,
    machine_config: NtxConfig = NTX_DEFAULT,
    closed: bool = False,
) -> DeburrResult:
    """Run the complete deburring pipeline for an edge chain.

    Args:
        samples: Sampled edge points with ``position``, ``tangent``,
            ``guide_normal``, ``other_normal`` attributes.
        tool: Cutter geometry and parameters.
        operation: Cutting parameters and motion mode.
        machine_config: NTX kinematics configuration.
        closed: Whether the edge chain forms a closed loop.

    Returns:
        DeburrResult with model-space and machine-space toolpaths.
    """
    warnings = []

    # --- preprocess flip_side ---
    processed_samples = _preprocess_samples(samples, operation.flip_side)

    # --- contact solve ---
    if tool.kind is ToolKind.BALL:
        try:
            analytic = solve_ball_cut(
                processed_samples,
                ball_radius=tool.radius,
                break_width=operation.ball_break_width,
                ball_engagement=operation.ball_engagement,
                lead_deg=operation.lead_deg if not _is_indexed_ball(tool, operation) else 0.0,
                tilt_deg=operation.tilt_deg if not _is_indexed_ball(tool, operation) else 0.0,
            )
        except BallSolverError as e:
            raise PipelineError("Ball contact solve failed: %s" % e)
    elif tool.kind is ToolKind.CHAMFER:
        if not tool.included_angle_deg:
            raise PipelineError("Chamfer tool requires included_angle_deg")
        if not tool.contact_radius:
            raise PipelineError("Chamfer tool requires contact_radius")
        try:
            analytic = solve_chamfer_cut(
                processed_samples,
                included_angle_deg=tool.included_angle_deg,
                contact_radius=tool.contact_radius + tool.radial_correction,
                tip_flat_diameter=tool.tip_flat_diameter,
                target_width=operation.target_width or 0.5,
                axial_correction=tool.axial_correction,
                lead_deg=operation.lead_deg,
            )
        except ChamferSolverError as e:
            raise PipelineError("Chamfer contact solve failed: %s" % e)
    else:
        raise PipelineError("Unknown tool kind: %s" % tool.kind)

    # --- posture realization ---
    if operation.motion_mode is MotionMode.INDEXED_3_PLUS_2:
        indexed_b, indexed_c = _resolve_indexed_angles(analytic, tool, operation, machine_config)
        realized = _realize_indexed(analytic, tool, indexed_b, indexed_c, machine_config)
    elif operation.motion_mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
        indexed_c = _resolve_fixed_c(analytic, operation, machine_config)
        indexed_b = None
        realized = _realize_4plus1(analytic, tool, indexed_c, machine_config)
    else:
        indexed_b, indexed_c = None, None
        realized = _realize_5axis(analytic, tool, machine_config)

    # --- closure (closed loop return to C0) ---
    if closed and realized:
        realized = realized + (realized[0],)

    # --- approach / retract ---
    with_motion = _add_approach_and_retract(realized, tool, operation)

    # --- spring passes ---
    with_springs = _apply_spring_passes(with_motion, operation)

    # --- machine coordinate solve ---
    machine_path = solve_ntx_toolpath(
        with_springs,
        config=machine_config,
        motion_mode=operation.motion_mode,
        indexed_b_deg=indexed_b,
        indexed_c_deg=indexed_c,
        feed=operation.feed,
    )

    # --- validate machine path ---
    warnings.extend(_validate_machine_path(machine_path, machine_config))

    model_path = Toolpath(
        points=tuple(
            PathPoint(
                seq=pt.seq if hasattr(pt, "seq") else i,
                xyz=pt.xyz,
                tool_axis=pt.tool_axis,
                motion=MotionKind.CUT,
                tangent=pt.tangent if hasattr(pt, "tangent") else None,
                feed=operation.feed,
            )
            for i, pt in enumerate(analytic)
        ),
    )

    return DeburrResult(
        model_path=model_path,
        machine_path=machine_path,
        indexed_b_deg=indexed_b,
        indexed_c_deg=indexed_c,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    pass


# ---------------------------------------------------------------------------
# Sample preprocessing
# ---------------------------------------------------------------------------

def _preprocess_samples(samples, flip_side: bool):
    if not flip_side:
        return samples
    result = []
    for s in samples:
        result.append(
            _ProxySample(
                position=s.position,
                tangent=s.tangent,
                guide_normal=(-s.guide_normal[0], -s.guide_normal[1], -s.guide_normal[2]),
                other_normal=(-s.other_normal[0], -s.other_normal[1], -s.other_normal[2]),
            )
        )
    return result


class _ProxySample:
    __slots__ = ("position", "tangent", "guide_normal", "other_normal")

    def __init__(self, position, tangent, guide_normal, other_normal):
        self.position = position
        self.tangent = tangent
        self.guide_normal = guide_normal
        self.other_normal = other_normal


# ---------------------------------------------------------------------------
# Posture resolution
# ---------------------------------------------------------------------------

def _is_indexed_ball(tool, operation):
    return tool.kind is ToolKind.BALL and operation.motion_mode is MotionMode.INDEXED_3_PLUS_2


def _resolve_indexed_angles(analytic, tool, operation, config):
    if not operation.auto_index and operation.indexed_b_deg is not None:
        return operation.indexed_b_deg, operation.indexed_c_deg

    if tool.kind is ToolKind.BALL:
        return _cardinal_ball_posture(analytic, tool, config)
    avg = _average_axis(analytic)
    return bc_from_axis_model(avg, config)


def _resolve_fixed_c(analytic, operation, config):
    if not operation.auto_index and operation.indexed_c_deg is not None:
        return operation.indexed_c_deg
    angles = [bc_from_axis_model(pt.tool_axis, config)[1] for pt in analytic]
    sines = sum(math.sin(math.radians(v)) for v in angles)
    cosines = sum(math.cos(math.radians(v)) for v in angles)
    return math.degrees(math.atan2(sines, cosines))


def _average_axis(analytic):
    v = [0.0, 0.0, 0.0]
    for pt in analytic:
        for i in range(3):
            v[i] += pt.tool_axis[i]
    mag = math.sqrt(sum(x * x for x in v))
    if mag < EPS:
        return analytic[0].tool_axis
    return tuple(x / mag for x in v)


def _cardinal_ball_posture(analytic, tool, config):
    preferences = [_ball_preference(pt, tool) for pt in analytic]
    v = [0.0, 0.0, 0.0]
    for p in preferences:
        for i in range(3):
            v[i] += p[i]
    mag_sq = sum(x * x for x in v)
    preferred_axis = tuple(x / math.sqrt(mag_sq) for x in v) if mag_sq > EPS else preferences[0]
    _, preferred_c = bc_from_axis_model(preferred_axis, config)

    candidates = []
    for order, physical_b in enumerate((0.0, -90.0, 90.0)):
        b = config.b_zero_offset_deg + config.b_branch_sign * physical_b
        if not config.b_min_deg <= b <= config.b_max_deg:
            continue
        c = preferred_c if physical_b == 0.0 else config.c_zero_offset_deg
        c_equiv = _equivalent_c_in_limits(c, config)
        if c_equiv is None:
            continue
        axis = axis_model_from_bc(b, c_equiv, config)
        alignment = sum(
            1.0 - max(-1.0, min(1.0, _dot3(axis, pref)))
            for pref in preferences
        )
        tangent_cost = sum(
            abs(_dot3(axis, _normalize3(getattr(pt, "tangent", (0, 0, 1)))))
            for pt in analytic
        )
        candidates.append((alignment + tangent_cost * 0.25, order, b, c_equiv))
    if not candidates:
        raise PipelineError("No B0/B±90 indexed ball posture is inside machine limits")
    _, _, indexed_b, indexed_c = min(candidates)
    return indexed_b, indexed_c


def _ball_preference(pt, tool):
    center = _add3(pt.xyz, _scale3(pt.tool_axis, tool.radius))
    direction = _sub3(center, pt.contact_xyz)
    return _normalize3(direction)


def _equivalent_c_in_limits(c, config):
    if config.c_min_deg is None and config.c_max_deg is None:
        return c
    for option in (c - 360.0, c, c + 360.0):
        if (config.c_min_deg is None or option >= config.c_min_deg) and (
            config.c_max_deg is None or option <= config.c_max_deg
        ):
            return option
    return None


# ---------------------------------------------------------------------------
# Realization (tool tip recomputation for machine-realizable axis)
# ---------------------------------------------------------------------------

def _realize_indexed(analytic, tool, b_deg, c_deg, config):
    fixed_axis = axis_model_from_bc(b_deg, c_deg, config)
    if tool.kind is ToolKind.BALL:
        return _realize_ball_points(analytic, fixed_axis, tool)
    else:
        return _realize_chamfer_points(analytic, fixed_axis, tool)


def _realize_4plus1(analytic, tool, c_deg, config):
    result = []
    for pt in analytic:
        b = b_for_fixed_c_axis(pt.tool_axis, c_deg, config)
        axis = axis_model_from_bc(b, c_deg, config)
        if tool.kind is ToolKind.BALL:
            result.append(_realize_ball_point(pt, axis, tool))
        else:
            result.append(_realize_chamfer_point(pt, axis, tool))
    return tuple(result)


def _realize_5axis(analytic, tool, config):
    result = []
    prev_c = None
    for pt in analytic:
        b, c = bc_from_axis_model(pt.tool_axis, config, prev_c)
        prev_c = c
        axis = axis_model_from_bc(b, c, config)
        if tool.kind is ToolKind.BALL:
            result.append(_realize_ball_point(pt, axis, tool))
        else:
            result.append(_realize_chamfer_point(pt, axis, tool))
    return tuple(result)


# -- Ball realization: preserve sphere center --

def _realize_ball_points(analytic, axis, tool):
    return tuple(_realize_ball_point(pt, axis, tool) for pt in analytic)


def _realize_ball_point(pt, axis, tool):
    axis = _normalize3(axis)
    center = _add3(pt.xyz, _scale3(pt.tool_axis, tool.radius))
    new_xyz = _sub3(center, _scale3(axis, tool.radius))
    return _RealizedPoint(xyz=new_xyz, tool_axis=axis, contact_xyz=pt.contact_xyz, tangent=pt.tangent)


# -- Chamfer realization: preserve contact point, verify tangency --
TANGENCY_TOL = 1e-5


def _realize_chamfer_points(analytic, axis, tool):
    return tuple(_realize_chamfer_point(pt, axis, tool) for pt in analytic)


def _realize_chamfer_point(pt, axis, tool):
    half_angle = math.radians(tool.included_angle_deg * 0.5)
    sin_a = math.sin(half_angle)
    cos_a = math.cos(half_angle)
    tan_a = math.tan(half_angle)
    tip_radius = tool.tip_flat_diameter * 0.5
    contact_radius = (tool.contact_radius or 0) + tool.radial_correction
    ax_dist = (contact_radius - tip_radius) / tan_a + tool.axial_correction

    old_radial = _normalize3(
        _scale3(
            _sub3(_sub3(pt.contact_xyz, pt.xyz), _scale3(pt.tool_axis, ax_dist)),
            1.0 / max(contact_radius, EPS),
        )
    )
    chamfer_normal = _normalize3(
        _sub3(_scale3(pt.tool_axis, sin_a), _scale3(old_radial, cos_a))
    )
    axis_n = _normalize3(axis)
    error = abs(_dot3(chamfer_normal, axis_n) - sin_a)
    if error > TANGENCY_TOL:
        raise PipelineError(
            "Cannot preserve chamfer tangency at the requested indexed angle "
            "(posture error %.6g). Use 4+1 or 5-axis mode." % error
        )
    new_radial = _normalize3(
        _scale3(
            _sub3(_scale3(axis_n, sin_a), chamfer_normal),
            1.0 / cos_a,
        )
    )
    new_xyz = _sub3(
        _sub3(pt.contact_xyz, _scale3(axis_n, ax_dist)),
        _scale3(new_radial, contact_radius),
    )
    return _RealizedPoint(
        xyz=new_xyz, tool_axis=axis_n, contact_xyz=pt.contact_xyz, tangent=pt.tangent
    )


class _RealizedPoint:
    __slots__ = ("xyz", "tool_axis", "contact_xyz", "tangent")

    def __init__(self, xyz, tool_axis, contact_xyz, tangent):
        self.xyz = xyz
        self.tool_axis = tool_axis
        self.contact_xyz = contact_xyz
        self.tangent = tangent


# ---------------------------------------------------------------------------
# Approach/retract
# ---------------------------------------------------------------------------

def _add_approach_and_retract(cuts, tool, operation):
    if len(cuts) < 2:
        return tuple(cuts)
    first, last = cuts[0], cuts[-1]
    tan_f = _normalize3(first.tangent or (1, 0, 0))
    tan_l = _normalize3(last.tangent or (1, 0, 0))
    lead_start = _sub3(first.xyz, _scale3(tan_f, operation.lead_in_length))
    lead_end = _add3(last.xyz, _scale3(tan_l, operation.lead_out_length))
    safe_start = _add3(lead_start, _scale3(first.tool_axis, operation.safety_lift))
    safe_end = _add3(lead_end, _scale3(last.tool_axis, operation.safety_lift))
    result = [
        _RealizedPoint(xyz=safe_start, tool_axis=first.tool_axis, contact_xyz=None, tangent=tan_f),
        _RealizedPoint(xyz=lead_start, tool_axis=first.tool_axis, contact_xyz=None, tangent=tan_f),
    ]
    result.extend(cuts)
    result.append(
        _RealizedPoint(xyz=lead_end, tool_axis=last.tool_axis, contact_xyz=None, tangent=tan_l)
    )
    result.append(
        _RealizedPoint(xyz=safe_end, tool_axis=last.tool_axis, contact_xyz=None, tangent=tan_l)
    )
    return tuple(result)


# ---------------------------------------------------------------------------
# Spring passes
# ---------------------------------------------------------------------------

def _apply_spring_passes(points, operation):
    if operation.spring_passes <= 0:
        return tuple(points)
    result = list(points)
    reduced_feed = operation.feed * operation.spring_feed_fraction
    for _ in range(operation.spring_passes - 1):
        result.extend(points)
    return tuple(result)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_machine_path(machine_path, config):
    warnings = []
    for i, pt in enumerate(machine_path.points):
        if pt.b_deg < config.b_min_deg - 1e-6 or pt.b_deg > config.b_max_deg + 1e-6:
            warnings.append("B-axis limit exceeded at point %d: B=%.3f (range %.1f to %.1f)" %
                            (i, pt.b_deg, config.b_min_deg, config.b_max_deg))
        if pt.tool_axis is not None:
            for v in pt.tool_axis:
                if not math.isfinite(v):
                    warnings.append("Non-finite tool axis at point %d" % i)
    if i > 0:
        for p, n in zip(machine_path.points, machine_path.points[1:]):
            if abs(n.b_deg - p.b_deg) > config.max_b_step_deg:
                warnings.append("B-step exceeds limit at seq %d→%d: %.2f°" %
                                (p.seq, n.seq, abs(n.b_deg - p.b_deg)))
            if abs(n.c_deg - p.c_deg) > config.max_c_step_deg:
                warnings.append("C-step exceeds limit at seq %d→%d: %.2f°" %
                                (p.seq, n.seq, abs(n.c_deg - p.c_deg)))
    return warnings


# ---------------------------------------------------------------------------
# Vector helpers (minimal, no external deps)
# ---------------------------------------------------------------------------

def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add3(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale3(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _normalize3(a):
    mag = math.sqrt(_dot3(a, a))
    if mag < EPS:
        return (0.0, 0.0, 1.0)
    return (a[0] / mag, a[1] / mag, a[2] / mag)
