"""Feed planning — path-velocity and feed-rate optimization.

Computes feed rates along the toolpath for:
- Constant material removal rate (adaptive feed)
- Chordal deviation limiting (slower on curves)
- Machine acceleration limits (corner deceleration)
- Safe rapid traverse (G00) planning

The feed planner runs after smoothing and before NC post-processing.

TODO:
 - Adaptive feed from engagement volume
 - Corner deceleration profiles
 - Machine acceleration/jerk limit integration
 - G-code F-word optimization
"""

from __future__ import annotations

from typing import List, Optional, Tuple

Vec3 = Tuple[float, float, float]


def constant_feed_plan(points: List[Vec3], base_feed: float) -> List[float]:
    """Assign the same feed rate to every cut segment."""
    return [base_feed] * len(points) if points else []


def chordal_feed_plan(
    points: List[Vec3],
    base_feed: float,
    chordal_tolerance: float = 0.01,
) -> List[float]:
    """Reduce feed on tight curves to respect chordal deviation.

    For each segment, compute the chordal deviation from the segment
    midpoint and scale feed proportionally.

    TODO: Implement chordal deviation calculation and feed scaling.
    """
    return [base_feed] * len(points) if points else []


def segment_lengths(points: List[Vec3]) -> List[float]:
    """Euclidean distances between consecutive points."""
    from math import sqrt

    dists = [0.0]
    for i in range(1, len(points)):
        a = points[i - 1]
        b = points[i]
        dists.append(sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))
    return dists
