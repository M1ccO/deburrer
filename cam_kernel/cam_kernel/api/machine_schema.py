"""Machine schema — kinematic chain, axis limits, and post configuration.

Defines the machine model that the kinematics, collision, and post-processing
layers all reference.  Separated from the kinematics solver so that multiple
machines can share the same solver library.

Bridges to ``fc_deburr.machine.profiles.MachineProfile`` and
``fc_deburr.machine.profiles.WorkpieceFrame``.

TODO:
 - Support non-NTX machine topologies (tilting-head, gantry, robot)
 - Import machine definitions from YAML/JSON
 - Add dynamic limits (velocity, acceleration, jerk) for feed planning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class MachineTopology(str, Enum):
    TABLE_TABLE = "table_table"
    HEAD_HEAD = "head_head"
    HEAD_TABLE = "head_table"
    TURN_MILL = "turn_mill"
    ROBOT = "robot"


@dataclass(frozen=True)
class LinearAxis:
    name: str
    min_mm: float = -1000.0
    max_mm: float = 1000.0
    max_velocity: float = 30000.0
    max_acceleration: float = 5000.0


@dataclass(frozen=True)
class RotaryAxis:
    name: str
    min_deg: Optional[float] = None
    max_deg: Optional[float] = None
    max_velocity: float = 20000.0
    max_acceleration: float = 5000.0
    unlimited: bool = False
    zero_offset_deg: float = 0.0
    direction_sign: float = 1.0


@dataclass(frozen=True)
class MachineDefinition:
    id: str
    family: MachineTopology = MachineTopology.TURN_MILL
    description: str = ""
    controller: str = "fanuc"
    units: str = "mm"
    linear_axes: Tuple[LinearAxis, ...] = ()
    rotary_axes: Tuple[RotaryAxis, ...] = ()
    diameter_programming: bool = True
    home_position: Tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0)
    tool_change_position: Tuple[float, ...] = (0.0, 0.0, 0.0, -90.0, 0.0)
    max_b_step_deg: float = 20.0
    max_c_step_deg: float = 45.0
    max_tangent_jump_deg: float = 30.0
    max_normal_jump_deg: float = 25.0

    @property
    def max_rotary_step(self) -> dict:
        return {"B": self.max_b_step_deg, "C": self.max_c_step_deg}


def ntx2500_default() -> MachineDefinition:
    return MachineDefinition(
        id="ntx_tcp_provisional",
        family=MachineTopology.TURN_MILL,
        linear_axes=(
            LinearAxis(name="X", max_mm=750.0),
            LinearAxis(name="Y", min_mm=-250.0, max_mm=250.0),
            LinearAxis(name="Z", max_mm=1540.0),
        ),
        rotary_axes=(
            RotaryAxis(name="B", min_deg=-120.0, max_deg=120.0),
            RotaryAxis(name="C", unlimited=True),
        ),
        diameter_programming=True,
    )
