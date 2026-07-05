"""NTX2500 kinematics model.

Encodes the axis layout, sign conventions, and limit data for the
DMG MORI NTX 2500 turn-mill machine:

- Linear axes: X (radial), Y (cross), Z (axial/spindle)
- Rotary axes: B (tool tilt, table), C (spindle rotation)
- B0 = radial (+X), B-90 = axial (+Z away from main-spindle face)
- C+ = clockwise when viewed from tool/subspindle toward main chuck

Bridges to ``fc_deburr.machine.profiles.MachineProfile`` which encodes
the same conventions as calibration data.

TODO:
 - Multi-machine support (NTX3000, CTX, DMU)
 - Automatic machine detection from controller probes
 - Temperature compensation models
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class Ntx2500Config:
    b_min_deg: float = -120.0
    b_max_deg: float = 120.0
    c_unlimited: bool = True
    diameter_programming: bool = True
    b_branch_sign: float = 1.0
    c_axis_sign: float = 1.0
    b_zero_offset_deg: float = 0.0
    c_zero_offset_deg: float = 0.0
    max_b_step_deg: float = 20.0
    max_c_step_deg: float = 45.0


NTX2500_DEFAULT = Ntx2500Config()


def model_to_machine_order() -> Tuple[int, int, int]:
    """NTX mapping: model (X,Y,Z) → machine (Z,Y,X)."""
    return (2, 1, 0)


def spindle_axis_model() -> Vec3:
    """NTX default spindle axis in model space."""
    return (1.0, 0.0, 0.0)


def axis_machine_from_b(b_deg: float, config: Ntx2500Config = NTX2500_DEFAULT) -> Vec3:
    """Tip-to-holder axis in machine coordinates.

    Bridges to ``fc_deburr.machine.kinematics.axis_machine_from_b``.
    """
    physical_b = (b_deg - config.b_zero_offset_deg) / config.b_branch_sign
    angle = math.radians(physical_b)
    return (math.cos(angle), 0.0, -math.sin(angle))
