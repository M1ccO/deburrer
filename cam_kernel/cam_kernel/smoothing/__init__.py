"""Smoothing layer — pose and joint-space filtering.

Post-processes the selected posture sequence for:
- Tool-path smoothing (G64 / corner blending)
- Joint-space filtering (B/C velocity continuity)
- Feed-rate planning (constant material removal rate, acceleration limits)

Smoothing happens after kinematics and before collision checking, so
the smoothed path is validated against limits and gouge checks run on
the final path.

The smoothing layer is deliberately separate from the posture optimizer
— the optimizer picks a globally optimal discrete sequence, and the
smoother produces a continuous, machine-realizable path from it.

TODO:
 - Pose-space FIR/IIR filtering
 - Joint-space jerk-limited trajectory generation
 - Constant-chordal-deviation feed adaptation
 - G64 corner-rounding parameters
"""

from __future__ import annotations

from typing import List, Optional
