"""Pose filter — part-space tool-axis smoothing.

Applies low-pass filtering to the tool-axis sequence to reduce
high-frequency orientation changes that cause jerky machine motion.

Uses a simple exponential moving average (EMA) with configurable
smoothing factor.  For production use, a jerk-limited FIR filter
or a B-spline interpolator would be more appropriate.

TODO:
 - Jerk-limited trajectory generation
 - B-spline interpolation for continuous curvature
 - Adaptive smoothing based on local curvature
"""

from __future__ import annotations

import math
from typing import List, Tuple

Vec3 = Tuple[float, float, float]


def ema_smooth_axes(
    axes: List[Vec3],
    alpha: float = 0.3,
) -> List[Vec3]:
    """Exponential moving average smoothing of tool-axis vectors.

    Each smoothed axis is re-normalised after blending.

    Args:
        axes: List of tool-axis vectors.
        alpha: Smoothing factor (0 = no smoothing, 1 = heavy).

    Returns:
        Smoothed axis vectors.
    """
    from fc_deburr.geometry.vectors import normalize, scale, add

    if not axes:
        return axes
    result = [axes[0]]
    for i in range(1, len(axes)):
        prev = result[-1]
        curr = axes[i]
        dot = prev[0] * curr[0] + prev[1] * curr[1] + prev[2] * curr[2]
        if dot < 0:
            curr = (-curr[0], -curr[1], -curr[2])
        blended = add(scale(prev, (1.0 - alpha)), scale(curr, alpha))
        result.append(normalize(blended))
    return result


def angular_velocity(axes: List[Vec3]) -> List[float]:
    """Compute angular velocity (deg per step) between consecutive axes."""
    from fc_deburr.geometry.vectors import angle_deg

    velocities = [0.0]
    for i in range(1, len(axes)):
        velocities.append(angle_deg(axes[i - 1], axes[i]))
    return velocities
