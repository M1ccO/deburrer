"""Engagement rules.

Defines the kinematic constraints on how a cutter engages with the
workpiece material:

- Ball engagement depth vs. effective radius
- Chamfer width limits based on tool geometry
- Stepover and scallop height for surface finishing
- Climb vs. conventional milling direction

These rules are used by the posture solver to reject or penalize
postures that would exceed the cutter's engagement capability.

TODO:
 - Material-specific feed/speed tables
 - Chip-thinning calculations
 - Adaptive engagement for corner transitions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EngagementParams:
    max_radial_engagement: float
    max_axial_engagement: float
    min_chip_thickness: float = 0.01
    climb_milling: bool = True


def ball_effective_radius(ball_radius: float, engagement_depth: float) -> float:
    """Effective cutting radius at the given engagement depth."""
    if engagement_depth >= ball_radius:
        raise ValueError("Engagement depth must be smaller than ball radius")
    import math

    return math.sqrt(ball_radius**2 - (ball_radius - engagement_depth) ** 2)


def chamfer_max_width(included_angle_deg: float, cutting_length: float) -> float:
    """Maximum chamfer width achievable with the current cutting length."""
    import math

    half_angle = (180.0 - included_angle_deg) / 2.0
    return cutting_length * math.cos(math.radians(half_angle))


def face_stepover(ball_radius: float, scallop_height: float) -> float:
    """Stepover distance for a given scallop height with a ball tool.

    s = 2 * sqrt(2*R*h - h^2)
    """
    import math

    return 2.0 * math.sqrt(2.0 * ball_radius * scallop_height - scallop_height**2)
