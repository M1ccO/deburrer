"""Contact layer — cutter-to-part contact solving.

Determines how the cutter touches the workpiece at each sample point.
Two backends are available:

1. **OCL bridge** — delegates to OpenCAMLib for drop-cutter and
   push-cutter algorithms (3D surface toolpaths).
2. **Local contact** — analytic contact for simple cutter/workpiece
   geometries (ball-on-edge, cone-on-edge).

The contact solver outputs ``ContactSolution`` values carrying the
cutter-reference position, tool axis, and contact point in part space.
These are the inputs to the posture and kinematics layers.

Bridges to ``fc_deburr.solver.ball.solve_ball_cut`` and
``fc_deburr.solver.chamfer.solve_chamfer_cut`` for the existing
analytic edge deburring solvers.
"""
