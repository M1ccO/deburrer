"""Axis seeding — initial tool-axis candidates.

Generates one or more tool-axis candidates at each contact point.
The seed is the starting direction for posture optimization:

- **Bisector seed**: tool axis aligned with the edge bisector (natural
  chamfer orientation).
- **Lead/tilt offsets**: rotate the bisector by user-specified lead
  (around tangent) and tilt (around binormal).
- **Surface-normal seed**: tool axis aligned with the face normal
  (for surface finishing).
- **Hemisphere sweep**: generate multiple candidates by sweeping a
  cone or hemisphere around the base direction.

Each seed is a plain Vec3 — the posture layer and kinematics layer
determine whether it is physically realizable.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

Vec3 = Tuple[float, float, float]


def bisector_seed(sample) -> Vec3:
    """Default tool-axis seed: the bisector of the two face normals.

    Bridges to ``fc_deburr.solver.posture``.
    """
    from fc_deburr.geometry.vectors import normalize

    return normalize(
        (
            sample.guide_normal[0] + sample.other_normal[0],
            sample.guide_normal[1] + sample.other_normal[1],
            sample.guide_normal[2] + sample.other_normal[2],
        )
    )


def lead_tilt_seed(
    sample, lead_deg: float = 0.0, tilt_deg: float = 0.0
) -> Vec3:
    """Rotate the bisector by lead (around tangent) and tilt (around binormal).

    Bridges to ``fc_deburr.solver`` lead/tilt rotation.
    """
    from fc_deburr.geometry.vectors import cross, normalize, rotate_about_axis

    bisector = bisector_seed(sample)
    tangent = normalize(sample.tangent)
    binormal = normalize(cross(tangent, bisector))

    axis = bisector
    if abs(lead_deg) > 1.0e-6:
        axis = rotate_about_axis(axis, tangent, lead_deg)
    if abs(tilt_deg) > 1.0e-6:
        axis = rotate_about_axis(axis, binormal, tilt_deg)
    return normalize(axis)


def cone_sweep(
    base_axis: Vec3, cone_angle_deg: float, divisions: int = 8
) -> List[Vec3]:
    """Generate tool-axis candidates on a cone around the base axis.

    TODO: Implement cone sweep with Rodrigues rotation.
    """
    raise NotImplementedError("Cone sweep not yet implemented")


def hemisphere_samples(divisions: int = 16) -> List[Vec3]:
    """Generate uniformly distributed points on the upper hemisphere.

    TODO: Fibonacci sphere or geodesic dome sampling.
    """
    raise NotImplementedError("Hemisphere sampling not yet implemented")
