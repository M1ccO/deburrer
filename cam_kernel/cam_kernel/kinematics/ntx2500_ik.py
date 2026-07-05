"""NTX2500 inverse kinematics — tool axis to B/C.

Converts a part-space tool-axis vector to B/C machine angles.
Implements the primary NTX branch and C-axis unwrapping:

- ``axis_model_from_bc(b, c)`` → part-space tool axis
- ``bc_from_axis_model(axis, preferred_c)`` → B/C machine angles

Bridges to ``fc_deburr.machine.kinematics``:

.. code-block:: python

    from fc_deburr.machine.kinematics import (
        axis_model_from_bc,
        bc_from_axis_model,
        solve_ntx_bc,
        machine_to_model,
        model_to_machine,
    )

TODO:
 - Secondary branch enumeration (redundant C solutions)
 - Joint velocity / acceleration limits in IK
 - Singularity avoidance at B=0
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from .ntx2500_model import Ntx2500Config, NTX2500_DEFAULT

Vec3 = Tuple[float, float, float]


def axis_model_from_bc(b_deg: float, c_deg: float, config: Ntx2500Config = NTX2500_DEFAULT) -> Vec3:
    """Forward kinematics: B/C → part-space tool axis.

    Delegates to ``fc_deburr.machine.kinematics.axis_model_from_bc``.
    """
    from fc_deburr.machine.kinematics import axis_model_from_bc as _fn
    from fc_deburr.machine.profiles import MachineProfile

    profile = _to_profile(config)
    return _fn(b_deg, c_deg, profile)


def bc_from_axis_model(
    axis_model: Vec3,
    config: Ntx2500Config = NTX2500_DEFAULT,
    preferred_c_deg: Optional[float] = None,
) -> Tuple[float, float]:
    """Inverse kinematics: part-space tool axis → B/C.

    Delegates to ``fc_deburr.machine.kinematics.bc_from_axis_model``.
    """
    from fc_deburr.machine.kinematics import bc_from_axis_model as _fn
    from fc_deburr.machine.profiles import MachineProfile

    profile = _to_profile(config)
    return _fn(axis_model, profile, preferred_c_deg)


def solve_ntx_toolpath(path, config: Ntx2500Config = NTX2500_DEFAULT, motion_mode=None, indexed_b=None, indexed_c=None):
    """Full NTX toolpath IK — converts a part-space path to machine points.

    Delegates to ``fc_deburr.machine.kinematics.solve_ntx_bc``.
    """
    from fc_deburr.machine.kinematics import solve_ntx_bc
    from fc_deburr.machine.profiles import MachineProfile
    from fc_deburr.domain.models import MotionMode

    profile = _to_profile(config)
    mm = motion_mode or MotionMode.INDEXED_3_PLUS_2
    return solve_ntx_bc(path, profile, mm, indexed_b, indexed_c)


def _to_profile(config: Ntx2500Config):
    from fc_deburr.machine.profiles import MachineProfile

    return MachineProfile(
        id="ntx_tcp_provisional",
        b_min_deg=config.b_min_deg,
        b_max_deg=config.b_max_deg,
        max_b_step_deg=config.max_b_step_deg,
        max_c_step_deg=config.max_c_step_deg,
        diameter_programming=config.diameter_programming,
    )
