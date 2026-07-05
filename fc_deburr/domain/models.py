from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


class ToolKind(str, Enum):
    CHAMFER = "chamfer"
    BALL = "ball"


class FeatureSourceKind(str, Enum):
    WIRE = "wire"
    FACE = "face"


class PositioningMode(str, Enum):
    TANGENT = "tangent"
    CENTER = "center"


class MotionMode(str, Enum):
    INDEXED_3_PLUS_2 = "indexed_3_plus_2"
    SIMULTANEOUS_4_PLUS_1 = "simultaneous_4_plus_1"
    SIMULTANEOUS_5_AXIS = "simultaneous_5_axis"


class CAxisMode(str, Enum):
    """Legacy settings compatibility; use ``MotionMode`` for new code."""
    FIXED = "fixed"
    SIMULTANEOUS = "simultaneous"


class MotionKind(str, Enum):
    RAPID = "rapid"
    APPROACH = "approach"
    LEAD_IN = "lead_in"
    CUT = "cut"
    LEAD_OUT = "lead_out"
    RETRACT = "retract"


class CutDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True)
class FeatureSample:
    """One immutable sample of the source edge in FreeCAD model space."""

    position: Vec3
    tangent: Vec3
    guide_normal: Vec3
    other_normal: Vec3
    source_edge_id: str = ""


@dataclass(frozen=True)
class FeatureLoop:
    """Geometry owned by the domain after the FreeCAD adapter returns.

    Samples do not repeat the first point at the end.  Closure is represented
    by ``closed`` so solvers can close a cutting path without ambiguous duplicate
    ownership.
    """

    id: str
    samples: Tuple[FeatureSample, ...]
    closed: bool
    source_kind: FeatureSourceKind = FeatureSourceKind.WIRE
    center_xyz: Optional[Vec3] = None
    source_object_id: str = ""
    source_edge_ids: Tuple[str, ...] = ()
    guide_face_id: str = ""
    c0_vertex_id: str = ""
    reversed_from_selection: bool = False


@dataclass(frozen=True)
class FacePatch:
    id: str
    brep: str
    area: float


@dataclass(frozen=True)
class FaceRegion:
    id: str
    patches: Tuple[FacePatch, ...]
    center_xyz: Vec3
    source_kind: FeatureSourceKind = FeatureSourceKind.FACE
    source_object_id: str = ""


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    kind: ToolKind
    diameter: float
    stickout: float
    cutting_length: float = 0.0
    included_angle_deg: Optional[float] = None
    tip_flat_diameter: float = 0.0
    tip_radius: float = 0.0
    contact_radius: Optional[float] = None
    radial_correction: float = 0.0
    axial_correction: float = 0.0


@dataclass(frozen=True)
class Operation:
    id: str
    tool_id: str
    target_width: Optional[float] = None
    ball_break_width: Optional[float] = None
    ball_engagement: Optional[float] = None
    feed: float = 800.0
    lead_deg: float = 0.0
    tilt_deg: float = 0.0
    lead_in_length: float = 2.0
    lead_out_length: float = 2.0
    safety_lift: float = 3.0
    positioning_mode: PositioningMode = PositioningMode.TANGENT
    flip_side: bool = False
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2
    auto_index: bool = True
    indexed_b_deg: Optional[float] = None
    indexed_c_deg: Optional[float] = None
    c_axis_mode: Optional[CAxisMode] = None
    surface_tolerance: float = 0.01
    surface_direction: str = "auto"
    path_sample_spacing: float = 0.5
    cut_direction: CutDirection = CutDirection.FORWARD
    spring_passes: int = 0
    spring_feed_fraction: float = 0.5


@dataclass(frozen=True)
class PathPoint:
    """A solver-owned cutter-reference position.

    ``xyz`` and the vector fields are in FreeCAD model space until the machine
    layer creates a new point carrying B/C values.
    """

    seq: int
    xyz: Vec3
    tool_axis: Vec3
    motion: MotionKind
    contact_xyz: Optional[Vec3] = None
    target_a_xyz: Optional[Vec3] = None
    target_b_xyz: Optional[Vec3] = None
    tangent: Optional[Vec3] = None
    feed: Optional[float] = None
    b_deg: Optional[float] = None
    c_deg: Optional[float] = None
    flags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Toolpath:
    feature_id: str
    operation_id: str
    tool_id: str
    points: Tuple[PathPoint, ...]
    warnings: Tuple[str, ...] = ()
    source_center_xyz: Optional[Vec3] = None


@dataclass(frozen=True)
class MachinePoint:
    """Machine-owned point in physical radius coordinates.

    X is stored as a physical radius here.  Diameter programming is a rendering
    concern owned exclusively by the postprocessor.
    """

    seq: int
    xyz_radius: Vec3
    b_deg: float
    c_deg: float
    motion: MotionKind
    feed: Optional[float] = None
    flags: Tuple[str, ...] = ()


def operation_motion_mode(operation: Operation) -> MotionMode:
    if operation.c_axis_mode is CAxisMode.FIXED:
        return MotionMode.INDEXED_3_PLUS_2
    if operation.c_axis_mode is CAxisMode.SIMULTANEOUS:
        return MotionMode.SIMULTANEOUS_5_AXIS
    return operation.motion_mode


@dataclass(frozen=True)
class MachineToolpath:
    feature_id: str
    operation_id: str
    tool_id: str
    points: Tuple[MachinePoint, ...]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    sample_index: Optional[int] = None
    is_error: bool = True


# Issue codes the UI and metrics can branch on.
ISSUE_B_LIMIT = "machine.b_limit"
ISSUE_C_LIMIT = "machine.c_limit"
ISSUE_C_STEP = "machine.c_step"
ISSUE_B_STEP = "machine.b_step"


@dataclass(frozen=True)
class ValidationReport:
    issues: Tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not any(issue.is_error for issue in self.issues)
