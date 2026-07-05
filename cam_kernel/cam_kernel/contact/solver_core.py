"""Standalone analytic contact solvers for edge deburring.

Pure vector math — no dependency on fc_deburr or any CAD library.
Accepts sampled edge points with face normals and returns tool-tip
positions (cutter reference points) suitable for kinematics resolution.

Solver styles (machining strategies):
  - **ball_on_edge** — ball endmill creating a rounded break along an edge
  - **chamfer_on_edge** — chamfer mill creating an equal-width flat chamfer
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]

EPSILON = 1.0e-10
POSTURE_TANGENCY_TOLERANCE = 1.0e-5


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3:
    mag = _length(a)
    if mag <= EPSILON:
        raise ValueError("Zero-length vector")
    return _scale(a, 1.0 / mag)


def _midpoint(a: Vec3, b: Vec3) -> Vec3:
    return _scale(_add(a, b), 0.5)


def _project_onto_plane(v: Vec3, plane_normal: Vec3) -> Vec3:
    n = _normalize(plane_normal)
    return _sub(v, _scale(n, _dot(v, n)))


def _rotate_about_axis(v: Vec3, axis: Vec3, angle_deg: float) -> Vec3:
    u = _normalize(axis)
    rad = math.radians(angle_deg)
    c = math.cos(rad)
    s = math.sin(rad)
    return _add(
        _add(_scale(v, c), _scale(_cross(u, v), s)),
        _scale(u, _dot(u, v) * (1.0 - c)),
    )


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SolverPoint:
    seq: int
    xyz: Vec3
    tool_axis: Vec3
    contact_xyz: Vec3
    tangent: Vec3
    guide_boundary: Optional[Vec3] = None
    other_boundary: Optional[Vec3] = None


# ---------------------------------------------------------------------------
# Ball solver — rounded break on edge
# ---------------------------------------------------------------------------

class BallSolverError(ValueError):
    pass


def solve_ball_cut(
    samples: Sequence,
    ball_radius: float,
    break_width: Optional[float] = None,
    ball_engagement: Optional[float] = None,
    lead_deg: float = 0.0,
    tilt_deg: float = 0.0,
) -> Tuple[SolverPoint, ...]:
    """Compute ball-tool positions for a rounded edge break.

    Each sample must expose ``position``, ``tangent``, ``guide_normal``,
    and ``other_normal`` as 3-tuples.

    Args:
        samples: Edge sample points with face normals.
        ball_radius: Ball endmill radius (diameter / 2).
        break_width: Target rounded-break width along each face.
        ball_engagement: Legacy radial engagement depth.
        lead_deg: Lead angle around the binormal (degrees).
        tilt_deg: Tilt angle around the tangent (degrees).
    """
    if ball_radius <= 0.0:
        raise BallSolverError("Ball radius must be positive")
    if break_width is not None:
        if break_width <= 0.0:
            raise BallSolverError("Break width must be positive")
        if break_width >= ball_radius:
            raise BallSolverError("Break width must be smaller than ball radius")
    elif ball_engagement is not None:
        if ball_engagement <= 0.0:
            raise BallSolverError("Ball engagement must be positive")
        if ball_engagement >= ball_radius:
            raise BallSolverError("Ball engagement must be smaller than ball radius")
    else:
        raise BallSolverError("Set break_width or ball_engagement")

    points = []
    for seq, sample in enumerate(samples):
        tangent = _normalize(sample.tangent)
        guide = _normalize(sample.guide_normal)
        other = _normalize(sample.other_normal)
        bisector = _normalize(_add(guide, other))

        tool_axis = bisector
        side_axis = _normalize(_cross(tangent, bisector))
        if abs(lead_deg) > 1e-6:
            tool_axis = _rotate_about_axis(tool_axis, side_axis, lead_deg)
        if abs(tilt_deg) > 1e-6:
            tool_axis = _rotate_about_axis(tool_axis, tangent, tilt_deg)
        tool_axis = _normalize(tool_axis)

        if break_width is not None:
            center_distance = _ball_center_distance(
                ball_radius,
                break_width,
                bisector,
                guide,
                other,
            )
        else:
            center_distance = ball_radius - ball_engagement
        ball_center = _add(sample.position, _scale(bisector, center_distance))
        tool_tip = _sub(ball_center, _scale(tool_axis, ball_radius))

        points.append(
            SolverPoint(
                seq=seq,
                xyz=tool_tip,
                tool_axis=tool_axis,
                contact_xyz=sample.position,
                tangent=tangent,
            )
        )

    return tuple(points)


def _ball_center_distance(
    radius: float,
    width: float,
    bisector: Vec3,
    guide_normal: Vec3,
    other_normal: Vec3,
) -> float:
    """Invert rounded-break width → ball-center distance from edge."""
    cosine_half = max(0.0, min(1.0, _dot(bisector, guide_normal)))
    guide_inward = _normalize(_project_onto_plane(_scale(other_normal, -1.0), guide_normal))
    sine_half = max(0.0, min(1.0, -_dot(bisector, guide_inward)))
    radicand = radius * radius - width * width * cosine_half * cosine_half
    if radicand <= 0.0:
        raise BallSolverError(
            "Requested rounded-break width is not reachable for the local face angle"
        )
    distance = math.sqrt(radicand) - width * sine_half
    if distance < 0.0:
        raise BallSolverError(
            "Requested rounded-break width places the ball center past the source edge"
        )
    return distance


# ---------------------------------------------------------------------------
# Chamfer solver — equal-width flat chamfer on edge
# ---------------------------------------------------------------------------

class ChamferSolverError(ValueError):
    pass


def solve_chamfer_cut(
    samples: Sequence,
    included_angle_deg: float,
    contact_radius: float,
    tip_flat_diameter: float = 0.0,
    target_width: float = 0.5,
    axial_correction: float = 0.0,
    lead_deg: float = 0.0,
) -> Tuple[SolverPoint, ...]:
    """Compute chamfer-tool positions producing an equal-face-width flat chamfer.

    The solver positions a conical cutter so that the cone is tangent to
    both adjacent faces at the specified width from the edge.  The tool
    axis is chosen closest to the guide-face normal while maintaining
    cone‑plane tangency.

    Args:
        samples: Edge sample points with face normals.
        included_angle_deg: Total included angle of the chamfer cone.
        contact_radius: Radial distance from tool axis where the cone touches
            the chamfer plane (must be > tip_flat_diameter/2 and < tool_radius).
        tip_flat_diameter: Flat diameter at the tool tip (0 for sharp).
        target_width: Desired chamfer width along each face.
        axial_correction: Physical calibration offset along the tool axis.
        lead_deg: Lead rotation around the chamfer plane normal (preserves tangency).
    """
    if not 0.0 < included_angle_deg < 180.0:
        raise ChamferSolverError("Included angle must be between 0 and 180 degrees")
    if target_width <= 0.0:
        raise ChamferSolverError("Chamfer width must be positive")
    if contact_radius <= 0.0:
        raise ChamferSolverError("Contact radius must be positive")

    half_angle = math.radians(included_angle_deg * 0.5)
    sin_alpha = math.sin(half_angle)
    cos_alpha = math.cos(half_angle)
    tan_alpha = math.tan(half_angle)
    if abs(cos_alpha) <= EPSILON or abs(tan_alpha) <= EPSILON:
        raise ChamferSolverError("Chamfer tool angle is numerically unstable")

    tip_radius = tip_flat_diameter * 0.5
    effective_cr = contact_radius
    if effective_cr <= tip_radius:
        raise ChamferSolverError("Contact radius must exceed the tool tip-flat radius")

    points = []
    for seq, sample in enumerate(samples):
        guide = _normalize(sample.guide_normal)
        other = _normalize(sample.other_normal)
        chamfer_normal = _normalize(_add(guide, other))

        guide_inward = _normalize(_project_onto_plane(_scale(other, -1.0), guide))
        other_inward = _normalize(_project_onto_plane(_scale(guide, -1.0), other))
        guide_boundary = _add(sample.position, _scale(guide_inward, target_width))
        other_boundary = _add(sample.position, _scale(other_inward, target_width))
        contact = _midpoint(guide_boundary, other_boundary)

        guide_plane_component = _normalize(
            _project_onto_plane(guide, chamfer_normal)
        )
        tool_axis = _normalize(
            _add(
                _scale(chamfer_normal, sin_alpha),
                _scale(guide_plane_component, cos_alpha),
            )
        )
        if abs(lead_deg) > 1e-6:
            tool_axis = _normalize(
                _rotate_about_axis(tool_axis, chamfer_normal, lead_deg)
            )

        radial = _normalize(
            _scale(
                _sub(_scale(tool_axis, sin_alpha), chamfer_normal),
                1.0 / cos_alpha,
            )
        )
        if abs(_dot(chamfer_normal, tool_axis) - sin_alpha) > POSTURE_TANGENCY_TOLERANCE:
            raise ChamferSolverError(
                "Cone-plane tangency violated at sample %d" % seq
            )

        axial_distance = (effective_cr - tip_radius) / tan_alpha + axial_correction
        tool_tip = _sub(
            _sub(contact, _scale(tool_axis, axial_distance)),
            _scale(radial, effective_cr),
        )
        points.append(
            SolverPoint(
                seq=seq,
                xyz=tool_tip,
                tool_axis=tool_axis,
                contact_xyz=contact,
                tangent=_normalize(sample.tangent),
                guide_boundary=guide_boundary,
                other_boundary=other_boundary,
            )
        )

    return tuple(points)
