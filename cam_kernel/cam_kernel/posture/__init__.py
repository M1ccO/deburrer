"""Posture layer — tool-axis selection and optimization.

Converts contact solutions into machine-realizable tool postures:

1. **Axis seeding** — compute initial tool-axis candidates from bisector,
   lead/tilt angles, and surface normals.
2. **Posture cost** — score each candidate on workspace limits, axis
   travel, soft-limit proximity, and branch continuity.
3. **Posture optimization** — select the globally optimal sequence of
   postures across the entire toolpath.

The posture layer is the bridge between part-space contact geometry and
machine-space joint configurations.  It does not own the kinematics
model (that lives in ``kinematics/``) but may call it to evaluate
feasibility.

Bridges to ``fc_deburr.kernel`` posture candidate logic and
``fc_deburr.solver.posture`` posture realization.
"""
