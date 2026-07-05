"""Posture cost — scoring functions for tool-axis candidates.

Each candidate posture receives a scalar cost computed from multiple
terms:

- **Deviation cost**: angular distance from the preferred tool axis
- **Travel cost**: angular change from the previous posture
- **Joint cost**: B/C motion magnitude (kinematics-aware)
- **Soft-limit cost**: penalty for approaching axis limits
- **Branch cost**: penalty for crossing the kinematics branch boundary

Costs are combined with configurable weights.  The default weights are
chosen so that the selector picks smooth, workable paths with minimal
unnecessary axis motion.

Bridges to ``fc_deburr.kernel.selection`` cost model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class PostureCost:
    deviation: float = 0.0
    travel: float = 0.0
    joint: float = 0.0
    soft_limit: float = 0.0
    branch_change: float = 0.0

    @property
    def total(self) -> float:
        return self.deviation + self.travel + self.joint + self.soft_limit + self.branch_change


@dataclass(frozen=True)
class CostWeights:
    deviation: float = 1.0
    travel: float = 2.0
    joint: float = 1.0
    soft_limit: float = 10.0
    branch_change: float = 50.0


def deviation_cost(axis: Vec3, preferred_axis: Vec3) -> float:
    """Angular deviation from the preferred tool axis (radians, scaled).

    Bridges to ``fc_deburr.kernel.selection``.
    """
    from fc_deburr.geometry.vectors import angle_deg

    return angle_deg(axis, preferred_axis) * 0.01


def travel_cost(axis: Vec3, previous_axis: Optional[Vec3]) -> float:
    """Angular travel from the previous posture."""
    if previous_axis is None:
        return 0.0
    from fc_deburr.geometry.vectors import angle_deg

    return angle_deg(axis, previous_axis) * 0.01


def joint_motion_cost(b_deg: float, c_deg: float, prev_b: Optional[float], prev_c: Optional[float]) -> float:
    """B/C joint motion cost."""
    if prev_b is None or prev_c is None:
        return 0.0
    db = abs(b_deg - prev_b) * 0.01
    dc = abs(c_deg - prev_c) * 0.01
    return db + dc


def soft_limit_cost(b_deg: float, b_min: float, b_max: float, margin_deg: float = 5.0) -> float:
    """Penalty for approaching the B-axis soft limits."""
    d_low = b_deg - (b_min + margin_deg)
    d_high = (b_max - margin_deg) - b_deg
    if d_low > 0 and d_high > 0:
        return 0.0
    return max(0.0, -d_low) + max(0.0, -d_high)


def evaluate_posture(
    axis: Vec3,
    preferred_axis: Vec3,
    b_deg: float,
    c_deg: float,
    prev_axis: Optional[Vec3],
    prev_b: Optional[float],
    prev_c: Optional[float],
    b_limits: tuple,
    weights: CostWeights = CostWeights(),
) -> PostureCost:
    return PostureCost(
        deviation=weights.deviation * deviation_cost(axis, preferred_axis),
        travel=weights.travel * travel_cost(axis, prev_axis),
        joint=weights.joint * joint_motion_cost(b_deg, c_deg, prev_b, prev_c),
        soft_limit=weights.soft_limit * soft_limit_cost(b_deg, b_limits[0], b_limits[1]),
        branch_change=0.0,
    )
