from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from ..domain.models import MotionKind, ToolDefinition, Vec3


class FeasibilityState(str, Enum):
    """Result of a part-space feasibility check."""

    NOT_CHECKED = "not_checked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EngagementLocation:
    """Solver-defined location of the active cutting region."""

    kind: str
    value_mm: Optional[float] = None


@dataclass(frozen=True)
class ContactIntent:
    """Part-space machining intent, independent of an output machine."""

    feature_id: str
    operation_id: str
    tool_id: str
    target_mode: str
    target_amount_mm: Optional[float] = None
    stock_to_remove_mm: Optional[float] = None
    preferred_engagement: Optional[EngagementLocation] = None


@dataclass(frozen=True)
class AssemblyComponent:
    kind: str
    diameter_mm: float
    length_mm: float
    axial_start_mm: float = 0.0


@dataclass(frozen=True)
class ToolAssembly:
    """Cutter plus future shank/holder collision descriptions.

    The current application supplies only ``cutter``.  The tuple fields create
    a stable seam for later collision primitives without changing presets.
    """

    cutter: ToolDefinition
    usable_flute_band_mm: Optional[Tuple[float, float]] = None
    shank_components: Tuple[AssemblyComponent, ...] = ()
    holder_components: Tuple[AssemblyComponent, ...] = ()


@dataclass(frozen=True)
class CandidateFeasibility:
    state: FeasibilityState
    reasons: Tuple[str, ...] = ()
    minimum_clearance_mm: Optional[float] = None


@dataclass(frozen=True)
class PostureCandidate:
    """One part-space cutter posture at one path station."""

    id: str
    station_index: int
    seq: int
    xyz: Vec3
    tool_axis: Vec3
    motion: MotionKind
    contact_xyz: Optional[Vec3] = None
    target_a_xyz: Optional[Vec3] = None
    target_b_xyz: Optional[Vec3] = None
    tangent: Optional[Vec3] = None
    feed: Optional[float] = None
    flags: Tuple[str, ...] = ()
    engagement: Optional[EngagementLocation] = None
    local_cost: float = 0.0
    preferred_deviation_deg: float = 0.0
    feasibility: CandidateFeasibility = field(
        default_factory=lambda: CandidateFeasibility(
            FeasibilityState.NOT_CHECKED
        )
    )


@dataclass(frozen=True)
class CandidateStation:
    index: int
    candidates: Tuple[PostureCandidate, ...]


@dataclass(frozen=True)
class CandidateGraph:
    feature_id: str
    operation_id: str
    tool_id: str
    stations: Tuple[CandidateStation, ...]
    closed: bool = False


@dataclass(frozen=True)
class MachineCandidate:
    """One machine-space realization of a part-space posture."""

    id: str
    source: PostureCandidate
    xyz_radius: Vec3
    b_deg: float
    c_deg: float
    branch_id: str
    b_limit_margin_deg: float
    c_limit_margin_deg: Optional[float] = None
    machine_feasible: bool = True
    rejection_reasons: Tuple[str, ...] = ()
    local_cost: float = 0.0
    transition_cost_bias: float = 0.0
    soft_limit_cost: float = 0.0


@dataclass(frozen=True)
class MachineCandidateStation:
    index: int
    candidates: Tuple[MachineCandidate, ...]


@dataclass(frozen=True)
class MachineCandidateGraph:
    feature_id: str
    operation_id: str
    tool_id: str
    stations: Tuple[MachineCandidateStation, ...]
    closed: bool = False


@dataclass(frozen=True)
class SelectionWeights:
    posture_deviation: float = 1.0
    tool_axis_transition: float = 1.0
    b_axis_transition: float = 0.1
    c_axis_transition: float = 0.2
    soft_limit: float = 1.0
    branch_change: float = 100.0


@dataclass(frozen=True)
class SelectedSequence:
    candidates: Tuple[MachineCandidate, ...]
    total_cost: float


@dataclass(frozen=True)
class KernelDiagnostic:
    code: str
    message: str
    station_index: Optional[int] = None
    candidate_id: Optional[str] = None
    severity: str = "info"
