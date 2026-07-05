"""Tool schema — cutter and holder definitions.

Defines the complete tool assembly required for contact solving:
cutting geometry, holder geometry, and calibration offsets.

Bridges to ``fc_deburr.domain.models.ToolDefinition`` for the existing
analytic solvers while adding holder and engagement metadata for the
OCCT-based collision pipeline.

TODO:
 - Add holder geometry from STEP imports
 - Support user-defined tool libraries (YAML/JSON)
 - Add wear compensation and tool-life tracking fields
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ToolKind(str, Enum):
    CHAMFER = "chamfer"
    BALL = "ball"
    BULL = "bull"
    DRILL = "drill"
    TAP = "tap"


@dataclass(frozen=True)
class HolderDefinition:
    id: str
    description: str = ""
    taper: str = "BT40"
    gauge_length: float = 0.0
    body_diameter: float = 50.0
    nose_diameter: float = 30.0
    nose_length: float = 20.0
    step_file: str = ""


@dataclass(frozen=True)
class CutterDefinition:
    id: str
    kind: ToolKind
    diameter: float
    stickout: float
    cutting_length: float = 0.0
    included_angle_deg: Optional[float] = None
    tip_flat_diameter: float = 0.0
    tip_radius: float = 0.0
    corner_radius: float = 0.0
    contact_radius: Optional[float] = None
    radial_correction: float = 0.0
    axial_correction: float = 0.0
    flutes: int = 2
    max_rpm: float = 20000.0
    coating: str = ""


@dataclass(frozen=True)
class ToolAssembly:
    id: str
    cutter: CutterDefinition
    holder: HolderDefinition
    stickout: float

    @property
    def total_length(self) -> float:
        return self.holder.gauge_length + self.stickout


def cutter_from_tool_def(tool_def) -> CutterDefinition:
    """Convert an ``fc_deburr.domain.models.ToolDefinition`` to a ``CutterDefinition``."""
    return CutterDefinition(
        id=tool_def.id,
        kind=ToolKind(tool_def.kind.value),
        diameter=tool_def.diameter,
        stickout=tool_def.stickout,
        cutting_length=tool_def.cutting_length,
        included_angle_deg=tool_def.included_angle_deg,
        tip_flat_diameter=tool_def.tip_flat_diameter,
        tip_radius=tool_def.tip_radius,
        contact_radius=tool_def.contact_radius,
        radial_correction=tool_def.radial_correction,
        axial_correction=tool_def.axial_correction,
    )
