"""Joint filter — B/C joint-space smoothing.

Smooths the B/C angle sequence to ensure:
- No single-step exceeds max_b_step_deg / max_c_step_deg
- Joint velocities stay within machine limits
- C-axis unwrapping is preserved through smoothing

Uses a moving-average filter with configurable window size.
For production use, a jerk-limited spline would be used.

TODO:
 - Spline-based joint smoothing (B-spline / quaternion)
 - Velocity and acceleration limit enforcement
 - C-axis unwrap preservation during filtering
"""

from __future__ import annotations

from typing import List, Tuple


def moving_average_smooth(
    b_values: List[float],
    c_values: List[float],
    window: int = 3,
) -> Tuple[List[float], List[float]]:
    """Simple moving-average smoothing of B/C joint values.

    Window size of 1 returns the input unchanged.
    """
    if not b_values or window <= 1:
        return b_values, c_values

    def _smooth(values, w):
        result = []
        half = w // 2
        for i in range(len(values)):
            start = max(0, i - half)
            end = min(len(values), i + half + 1)
            window_slice = values[start:end]
            result.append(sum(window_slice) / len(window_slice))
        return result

    return _smooth(b_values, window), _smooth(c_values, window)


def check_joint_steps(
    b_values: List[float],
    c_values: List[float],
    max_b_step: float = 20.0,
    max_c_step: float = 45.0,
) -> List[str]:
    """Return warnings for steps exceeding machine limits."""
    warnings = []
    for i in range(1, len(b_values)):
        if abs(b_values[i] - b_values[i - 1]) > max_b_step:
            warnings.append(f"B-step {abs(b_values[i] - b_values[i - 1]):.1f} > {max_b_step} at index {i}")
        if abs(c_values[i] - c_values[i - 1]) > max_c_step:
            warnings.append(f"C-step {abs(c_values[i] - c_values[i - 1]):.1f} > {max_c_step} at index {i}")
    return warnings
