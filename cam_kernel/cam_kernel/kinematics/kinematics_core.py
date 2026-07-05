"""Standalone NTX kinematics — part-space ↔ machine-space conversions.

Pure math with no dependency on fc_deburr or any CAD library.

NTX 2500 axis convention (machine coords):
  - Machine X  = radial distance from spindle axis (→ diameter axis)
  - Machine Y  = cross direction
  - Machine Z  = spindle axis
  - B rotates the tool head (B0 = radial, B-90 = axial toward main spindle)
  - C rotates the workpiece around spindle axis

Model convention (FreeCAD model coords):
  - Model X = spindle axis
  - Model Y = radial reference direction (C0 reference)
  - Model Z = second radial (diameter axis)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Motion modes
# ---------------------------------------------------------------------------

class MotionMode(str, Enum):
    INDEXED_3_PLUS_2 = "indexed_3_plus_2"
    SIMULTANEOUS_4_PLUS_1 = "simultaneous_4_plus_1"
    SIMULTANEOUS_5_AXIS = "simultaneous_5_axis"


# ---------------------------------------------------------------------------
# Machine configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NtxConfig:
    model_to_machine_order: Tuple[int, int, int] = (2, 1, 0)
    model_to_machine_signs: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    b_min_deg: float = -120.0
    b_max_deg: float = 120.0
    c_min_deg: Optional[float] = None
    c_max_deg: Optional[float] = None
    b_branch_sign: float = 1.0
    b_zero_offset_deg: float = 0.0
    c_axis_sign: float = 1.0
    c_zero_offset_deg: float = 0.0
    max_b_step_deg: float = 20.0
    max_c_step_deg: float = 45.0
    diameter_programming: bool = True
    workpiece_origin: Vec3 = (0.0, 0.0, 0.0)
    spindle_axis: Vec3 = (1.0, 0.0, 0.0)


NTX_DEFAULT = NtxConfig()


# ---------------------------------------------------------------------------
# Coordinate transforms
# ---------------------------------------------------------------------------

def model_to_machine(vector: Vec3, config: NtxConfig = NTX_DEFAULT) -> Vec3:
    return tuple(
        vector[config.model_to_machine_order[idx]] * config.model_to_machine_signs[idx]
        for idx in range(3)
    )


def machine_to_model(vector: Vec3, config: NtxConfig = NTX_DEFAULT) -> Vec3:
    result = [0.0, 0.0, 0.0]
    for machine_idx, model_idx in enumerate(config.model_to_machine_order):
        result[model_idx] = vector[machine_idx] / config.model_to_machine_signs[machine_idx]
    return tuple(result)


def workpiece_to_machine(point: Vec3, config: NtxConfig = NTX_DEFAULT) -> Vec3:
    return tuple(
        point[idx] - config.workpiece_origin[idx] for idx in range(3)
    )


# ---------------------------------------------------------------------------
# Forward kinematics — B/C → part-space tool axis
# ---------------------------------------------------------------------------

def _axis_machine_from_b(b_deg: float, config: NtxConfig = NTX_DEFAULT) -> Vec3:
    """Tip-to-holder axis in machine coordinates. B0 = +X, B-90 = +Z."""
    physical_b = (b_deg - config.b_zero_offset_deg) / config.b_branch_sign
    angle = math.radians(physical_b)
    return (math.cos(angle), 0.0, -math.sin(angle))


def axis_model_from_bc(
    b_deg: float, c_deg: float, config: NtxConfig = NTX_DEFAULT
) -> Vec3:
    """Forward kinematics: B/C → part-space tool axis."""
    physical_c = (c_deg - config.c_zero_offset_deg) / config.c_axis_sign
    machine_axis = _axis_machine_from_b(b_deg, config)
    zero_c_axis = _rotate_machine_z(machine_axis, physical_c)
    return _normalize(machine_to_model(zero_c_axis, config))


# ---------------------------------------------------------------------------
# Inverse kinematics — part-space tool axis → B/C
# ---------------------------------------------------------------------------

def bc_from_axis_model(
    axis_model: Vec3,
    config: NtxConfig = NTX_DEFAULT,
    preferred_c_deg: Optional[float] = None,
) -> Tuple[float, float]:
    """Inverse kinematics: part-space tool axis → (B, C) angles."""
    axis = _normalize(model_to_machine(axis_model, config))
    radial = math.hypot(axis[0], axis[1])
    if radial <= 1e-12:
        physical_c = (
            (preferred_c_deg - config.c_zero_offset_deg) / config.c_axis_sign
            if preferred_c_deg is not None
            else 0.0
        )
    else:
        physical_c = math.degrees(math.atan2(axis[1], axis[0]))
    physical_b = math.degrees(math.atan2(-axis[2], radial))
    b_deg = config.b_zero_offset_deg + config.b_branch_sign * physical_b
    c_deg = config.c_zero_offset_deg + config.c_axis_sign * physical_c
    if preferred_c_deg is not None:
        c_deg = _nearest_equivalent(c_deg, preferred_c_deg)
    return b_deg, c_deg


def b_for_fixed_c_axis(
    axis_model: Vec3,
    c_deg: float,
    config: NtxConfig = NTX_DEFAULT,
) -> float:
    """Compute B for a given tool axis when C is fixed (4+1 mode)."""
    axis = _normalize(model_to_machine(axis_model, config))
    physical_c = (c_deg - config.c_zero_offset_deg) / config.c_axis_sign
    in_b_plane = _rotate_machine_z(axis, -physical_c)
    physical_b = math.degrees(math.atan2(-in_b_plane[2], in_b_plane[0]))
    return config.b_zero_offset_deg + config.b_branch_sign * physical_b


# ---------------------------------------------------------------------------
# Path-level toolpath to machine-point conversion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MachinePoint:
    seq: int
    xyz_radius: Vec3
    b_deg: float
    c_deg: float
    motion_kind: str = "cut"
    feed: Optional[float] = None
    tool_axis: Optional[Vec3] = None


@dataclass(frozen=True)
class MachineToolpath:
    points: Tuple[MachinePoint, ...]
    motion_mode: str = "indexed_3_plus_2"

    @property
    def point_count(self) -> int:
        return len(self.points)


def solve_ntx_toolpath(
    path_points: Sequence,
    config: NtxConfig = NTX_DEFAULT,
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2,
    indexed_b_deg: Optional[float] = None,
    indexed_c_deg: Optional[float] = None,
    feed: Optional[float] = None,
) -> MachineToolpath:
    """Convert model-space solver points to machine coordinates with B/C.

    Args:
        path_points: SolverPoint-like objects with ``xyz`` and ``tool_axis``.
        config: Machine kinematics configuration.
        motion_mode: Indexed 3+2, simultaneous 4+1, or full 5-axis.
        indexed_b_deg: Fixed B angle (3+2 mode).
        indexed_c_deg: Fixed C angle (3+2/4+1 mode).
        feed: Cutting feed rate for G01 moves.
    """
    if not path_points:
        raise ValueError("Empty path")

    first = path_points[0]
    if isinstance(first, tuple):
        pts = [type("_Pt", (), {"xyz": p[0], "tool_axis": p[1]})() for p in path_points]
    else:
        pts = path_points

    if motion_mode is MotionMode.INDEXED_3_PLUS_2:
        if indexed_b_deg is None or indexed_c_deg is None:
            indexed_b_deg, indexed_c_deg = bc_from_axis_model(pts[0].tool_axis, config)
    elif motion_mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
        if indexed_c_deg is None:
            _, indexed_c_deg = bc_from_axis_model(pts[0].tool_axis, config)

    previous_c = indexed_c_deg
    machine_points = []
    for idx, pt in enumerate(pts):
        xyz_work = workpiece_to_machine(pt.xyz, config)
        xyz_radius = model_to_machine(xyz_work, config)

        if motion_mode is MotionMode.INDEXED_3_PLUS_2:
            b = float(indexed_b_deg)
            c = float(indexed_c_deg)
        elif motion_mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
            b = b_for_fixed_c_axis(pt.tool_axis, float(indexed_c_deg), config)
            c = float(indexed_c_deg)
        else:
            b, c = bc_from_axis_model(pt.tool_axis, config, previous_c)
            previous_c = c

        machine_points.append(
            MachinePoint(
                seq=idx,
                xyz_radius=xyz_radius,
                b_deg=b,
                c_deg=c,
                feed=feed if idx > 0 else None,
                motion_kind="cut",
                tool_axis=pt.tool_axis,
            )
        )

    return MachineToolpath(
        points=tuple(machine_points),
        motion_mode=motion_mode.value,
    )


# ---------------------------------------------------------------------------
# Rotation helpers
# ---------------------------------------------------------------------------

def _rotate_machine_z(vector: Vec3, angle_deg: float) -> Vec3:
    angle = math.radians(angle_deg)
    c = math.cos(angle)
    s = math.sin(angle)
    return (
        c * vector[0] - s * vector[1],
        s * vector[0] + c * vector[1],
        vector[2],
    )


def _nearest_equivalent(value: float, reference: float) -> float:
    return min(
        (value - 360.0, value, value + 360.0),
        key=lambda candidate: abs(candidate - reference),
    )


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3:
    mag = _length(a)
    if mag <= 1e-12:
        return (0.0, 0.0, 1.0)
    return (a[0] / mag, a[1] / mag, a[2] / mag)
