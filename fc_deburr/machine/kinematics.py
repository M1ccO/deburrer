"""Reversible NTX part-vector and B/C kinematics."""

from __future__ import annotations

import math
from typing import Optional, Tuple

from ..domain.errors import GeometryError
from ..domain.models import (
    MachinePoint,
    MachineToolpath,
    MotionMode,
    Toolpath,
    Vec3,
)
from ..geometry.vectors import normalize
from .profiles import MachineProfile, WorkpieceFrame


def model_to_machine(vector: Vec3, profile: MachineProfile) -> Vec3:
    return tuple(
        vector[profile.model_to_machine_order[index]]
        * profile.model_to_machine_signs[index]
        for index in range(3)
    )


def machine_to_model(vector: Vec3, profile: MachineProfile) -> Vec3:
    result = [0.0, 0.0, 0.0]
    for machine_index, model_index in enumerate(
        profile.model_to_machine_order
    ):
        result[model_index] = (
            vector[machine_index]
            / profile.model_to_machine_signs[machine_index]
        )
    return tuple(result)


def workpiece_to_machine(point: Vec3, frame: WorkpieceFrame) -> Vec3:
    return tuple(
        point[index] - frame.origin_xyz[index] for index in range(3)
    )


def axis_machine_from_b(
    b_deg: float, profile: MachineProfile
) -> Vec3:
    """Tip-to-holder axis in machine coordinates.

    B0 is radial +X. B-90 is axial +Z, away from the main-spindle face.
    """

    physical_b = (
        b_deg - profile.b_zero_offset_deg
    ) / profile.b_branch_sign
    angle = math.radians(physical_b)
    return (math.cos(angle), 0.0, -math.sin(angle))


def axis_model_from_bc(
    b_deg: float,
    c_deg: float,
    profile: MachineProfile,
) -> Vec3:
    physical_c = (
        c_deg - profile.c_zero_offset_deg
    ) / profile.c_axis_sign
    machine_axis = axis_machine_from_b(b_deg, profile)
    zero_c_axis = _rotate_machine_z(machine_axis, physical_c)
    return normalize(machine_to_model(zero_c_axis, profile))


def bc_from_axis_model(
    axis_model: Vec3,
    profile: MachineProfile,
    preferred_c_deg: Optional[float] = None,
) -> Tuple[float, float]:
    """Invert a part-space axis into the primary NTX B/C branch."""

    axis = normalize(model_to_machine(axis_model, profile))
    radial = math.hypot(axis[0], axis[1])
    if radial <= 1.0e-12:
        physical_c = (
            (
                preferred_c_deg - profile.c_zero_offset_deg
            )
            / profile.c_axis_sign
            if preferred_c_deg is not None
            else 0.0
        )
    else:
        physical_c = math.degrees(math.atan2(axis[1], axis[0]))
    physical_b = math.degrees(math.atan2(-axis[2], radial))
    b_deg = (
        profile.b_zero_offset_deg
        + profile.b_branch_sign * physical_b
    )
    c_deg = (
        profile.c_zero_offset_deg
        + profile.c_axis_sign * physical_c
    )
    if preferred_c_deg is not None:
        c_deg = _nearest_equivalent(c_deg, preferred_c_deg)
    return b_deg, c_deg


def rotate_model_about_spindle(
    point: Vec3,
    c_deg: float,
    profile: MachineProfile,
) -> Vec3:
    """Rotate a model point as the physical workpiece rotates by C."""

    relative = tuple(
        point[index] - profile.workpiece.origin_xyz[index]
        for index in range(3)
    )
    machine = model_to_machine(relative, profile)
    physical_c = (
        c_deg - profile.c_zero_offset_deg
    ) / profile.c_axis_sign
    rotated = _rotate_machine_z(machine, -physical_c)
    model = machine_to_model(rotated, profile)
    return tuple(
        model[index] + profile.workpiece.origin_xyz[index]
        for index in range(3)
    )


def solve_ntx_bc(
    path: Toolpath,
    profile: MachineProfile,
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2,
    indexed_b_deg: Optional[float] = None,
    indexed_c_deg: Optional[float] = None,
) -> MachineToolpath:
    if not path.points:
        raise GeometryError("Cannot solve an empty toolpath")

    if motion_mode is MotionMode.INDEXED_3_PLUS_2:
        if indexed_b_deg is None or indexed_c_deg is None:
            indexed_b_deg, indexed_c_deg = bc_from_axis_model(
                path.points[0].tool_axis, profile
            )
    elif motion_mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
        if indexed_c_deg is None:
            _, indexed_c_deg = bc_from_axis_model(
                path.points[0].tool_axis, profile
            )

    previous_c = indexed_c_deg
    machine_points = []
    for index, point in enumerate(path.points):
        xyz_work = workpiece_to_machine(
            point.xyz, profile.workpiece
        )
        xyz = model_to_machine(xyz_work, profile)
        if motion_mode is MotionMode.INDEXED_3_PLUS_2:
            b_deg = float(indexed_b_deg)
            c_deg = float(indexed_c_deg)
        elif motion_mode is MotionMode.SIMULTANEOUS_4_PLUS_1:
            b_deg = _b_for_fixed_c_axis(
                point.tool_axis, float(indexed_c_deg), profile
            )
            c_deg = float(indexed_c_deg)
        else:
            b_deg, c_deg = bc_from_axis_model(
                point.tool_axis, profile, previous_c
            )
            previous_c = c_deg
        machine_points.append(
            MachinePoint(
                seq=index,
                xyz_radius=xyz,
                b_deg=b_deg,
                c_deg=c_deg,
                motion=point.motion,
                feed=point.feed,
                flags=point.flags,
            )
        )
    return MachineToolpath(
        feature_id=path.feature_id,
        operation_id=path.operation_id,
        tool_id=path.tool_id,
        points=tuple(machine_points),
        warnings=path.warnings,
    )


def _b_for_fixed_c_axis(
    axis_model: Vec3,
    c_deg: float,
    profile: MachineProfile,
) -> float:
    axis = normalize(model_to_machine(axis_model, profile))
    physical_c = (
        c_deg - profile.c_zero_offset_deg
    ) / profile.c_axis_sign
    in_b_plane = _rotate_machine_z(axis, -physical_c)
    physical_b = math.degrees(
        math.atan2(-in_b_plane[2], in_b_plane[0])
    )
    return (
        profile.b_zero_offset_deg
        + profile.b_branch_sign * physical_b
    )


def fixed_c_out_of_plane(
    axis_model: Vec3,
    c_deg: float,
    profile: MachineProfile,
) -> float:
    axis = normalize(model_to_machine(axis_model, profile))
    physical_c = (
        c_deg - profile.c_zero_offset_deg
    ) / profile.c_axis_sign
    return abs(_rotate_machine_z(axis, -physical_c)[1])


def _rotate_machine_z(vector: Vec3, angle_deg: float) -> Vec3:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        cosine * vector[0] - sine * vector[1],
        sine * vector[0] + cosine * vector[1],
        vector[2],
    )


def _nearest_equivalent(value: float, reference: float) -> float:
    return min(
        (value - 360.0, value, value + 360.0),
        key=lambda candidate: abs(candidate - reference),
    )


def bisector_polar_deg(
    tool_axis_machine: Vec3, spindle_axis_machine: Vec3
) -> float:
    a = normalize(tool_axis_machine)
    s = normalize(spindle_axis_machine)
    cosine = max(
        -1.0,
        min(1.0, sum(a[index] * s[index] for index in range(3))),
    )
    return math.degrees(math.acos(cosine))


def wire_tangent_c_deg(tangent_machine: Vec3) -> float:
    return math.degrees(
        math.atan2(tangent_machine[1], tangent_machine[0])
    )


def _spindle_axis_machine(profile: MachineProfile) -> Vec3:
    return model_to_machine(profile.workpiece.spindle_axis, profile)
