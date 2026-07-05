from dataclasses import dataclass
from typing import Optional, Tuple

from ..domain.models import MotionKind, Vec3


@dataclass(frozen=True)
class PreviewPolyline:
    name: str
    points: Tuple[Vec3, ...]
    color: str
    closed: bool = False
    dashed: bool = False


@dataclass(frozen=True)
class PreviewVector:
    start: Vec3
    end: Vec3
    color: str


@dataclass(frozen=True)
class PreviewMarker:
    name: str
    position: Vec3
    color: str


@dataclass(frozen=True)
class PreviewToolGeometry:
    kind: str
    diameter: float
    stickout: float
    cutting_length: float = 0.0
    included_angle_deg: Optional[float] = None
    tip_flat_diameter: float = 0.0
    tip_radius: float = 0.0


@dataclass(frozen=True)
class PreviewToolPose:
    cutter_reference: Vec3
    tool_axis: Vec3
    tool_axis_b_only: Vec3
    motion: MotionKind
    machine_xyz_radius: Vec3
    b_deg: float
    c_deg: float
    part_rotation_deg: float


@dataclass(frozen=True)
class PreviewDocument:
    polylines: Tuple[PreviewPolyline, ...]
    vectors: Tuple[PreviewVector, ...]
    markers: Tuple[PreviewMarker, ...]
    b_values: Tuple[float, ...]
    c_values: Tuple[float, ...]
    warnings: Tuple[str, ...] = ()
    tool: Optional[PreviewToolGeometry] = None
    tool_poses: Tuple[PreviewToolPose, ...] = ()
    spindle_origin: Vec3 = (0.0, 0.0, 0.0)
    spindle_axis: Vec3 = (1.0, 0.0, 0.0)
