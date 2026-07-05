from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List


@dataclass(frozen=True)
class WorkpieceFrame:
    """Where the workpiece lives inside the FreeCAD model.

    The frame is expressed in FreeCAD model space.  ``origin_xyz`` is the
    spindle-zero (the point the part is registered to), and ``spindle_axis``
    is the unit vector that the lathe spindle rotates around in the model.

    The default matches the established NTX wire-deburr mapping where
    model X is the spindle axis, model Y and Z are the radial directions
    (model Z is the diameter axis that the post doubles).  Override these
    for parts that are mounted in a different orientation, or for a
    horizontal-spindle mill-turn.
    """

    origin_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    spindle_axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)


@dataclass(frozen=True)
class MachineProfile:
    """Calibratable NTX geometry and safety policy.

    Defaults encode the observed FreeCAD-to-NTX axis mapping but remain named
    calibration data rather than being hidden inside a postprocessor.
    """

    id: str = "ntx_tcp_provisional"
    calibrated: bool = False
    workpiece: WorkpieceFrame = WorkpieceFrame()
    model_to_machine_order: Tuple[int, int, int] = (2, 1, 0)
    model_to_machine_signs: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    # Provisional NTX convention: B0 is radial and B-90 is axial toward the
    # main-spindle end face.  Signs/zeros remain calibration data.
    b_branch_sign: float = 1.0
    b_zero_offset_deg: float = 0.0
    # C+ is clockwise when viewed from the tool/subspindle toward the main
    # chuck.  ``c_axis_sign`` permits builder-specific reversal.
    c_axis_sign: float = 1.0
    c_zero_offset_deg: float = 0.0
    start_c_at_zero: bool = False
    b_min_deg: float = -120.0
    b_max_deg: float = 120.0
    c_min_deg: Optional[float] = None
    c_max_deg: Optional[float] = None
    max_b_step_deg: float = 20.0
    max_c_step_deg: float = 45.0
    max_tangent_jump_deg: float = 30.0
    max_normal_jump_deg: float = 25.0
    diameter_programming: bool = True
    # When True, output the part in physical-radius coordinates (X is the
    # cutter's distance from the spindle axis).  The post doubles X to match
    # diameter programming on the NTX.
    store_xyz_as_radius: bool = True
