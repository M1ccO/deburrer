"""Job schema — the top-level CAM job description.

A job binds a part, feature selections, tooling, machine profile, fixtures,
stock, and process parameters into a single serializable document.  The kernel
reads a job, solves the requested operations, and emits validated machine
toolpaths and NC output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class FeatureSelectionType(str, Enum):
    EDGE_CHAINS = "edge_chains"
    FACE_REGIONS = "face_regions"


class OperationType(str, Enum):
    CHAMFER = "chamfer"
    BALL_DEBURR = "ball_deburr"
    FACE_FINISHING = "face_finishing"


class MotionMode(str, Enum):
    INDEXED_3_PLUS_2 = "indexed_3_plus_2"
    SIMULTANEOUS_4_PLUS_1 = "simultaneous_4_plus_1"
    SIMULTANEOUS_5_AXIS = "simultaneous_5_axis"


@dataclass(frozen=True)
class WorkpieceFrame:
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    spindle_axis: Tuple[float, float, float] = (1.0, 0.0, 0.0)


@dataclass(frozen=True)
class FeatureSelection:
    type: FeatureSelectionType
    label: str
    edge_ids: Tuple[str, ...] = ()
    face_ids: Tuple[str, ...] = ()
    sampling_spacing: float = 0.5
    operation: Optional[FeatureOperation] = None


@dataclass(frozen=True)
class FeatureOperation:
    type: OperationType
    width: Optional[float] = None
    ball_engagement: Optional[float] = None
    tool_id: str = ""


@dataclass(frozen=True)
class JobSpec:
    name: str
    part_file: str
    unit: str = "mm"
    workpiece_frame: WorkpieceFrame = field(default_factory=WorkpieceFrame)
    features: Tuple[FeatureSelection, ...] = ()
    tooling: Tuple[dict, ...] = ()
    machine_profile: str = "ntx_tcp_provisional"
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2
    indexed_b_deg: Optional[float] = None
    indexed_c_deg: Optional[float] = None
    fixture_files: Tuple[str, ...] = ()
    stock_file: Optional[str] = None
    feed: float = 800.0
    safety_lift: float = 3.0
    lead_in_length: float = 2.0
    lead_out_length: float = 2.0
    lead_deg: float = 0.0
    tilt_deg: float = 0.0
    coolant: bool = False
    program_number: int = 1000
    work_offset: str = "G54"


def load_job_yaml(path: str) -> JobSpec:
    """Parse a YAML job file and return a validated ``JobSpec``."""
    import yaml

    with open(path, "r") as fh:
        raw = yaml.safe_load(fh)

    job_raw = raw.get("job", raw)
    part_raw = job_raw.get("part", {})

    frame = WorkpieceFrame(
        origin=tuple(part_raw.get("workpiece_frame", {}).get("origin", (0, 0, 0))),
        spindle_axis=tuple(part_raw.get("workpiece_frame", {}).get("spindle_axis", (1, 0, 0))),
    )

    features = []
    for feat in job_raw.get("features", []):
        op = None
        if "operation" in feat:
            op_raw = feat["operation"]
            op = FeatureOperation(
                type=OperationType(op_raw["type"]),
                width=op_raw.get("width"),
                ball_engagement=op_raw.get("ball_engagement"),
                tool_id=op_raw.get("tool_id", ""),
            )
        features.append(
            FeatureSelection(
                type=FeatureSelectionType(feat["type"]),
                label=feat.get("label", ""),
                edge_ids=tuple(feat.get("selection", {}).get("edge_ids", ())),
                face_ids=tuple(feat.get("selection", {}).get("face_ids", ())),
                sampling_spacing=feat.get("sampling", {}).get("spacing", 0.5),
                operation=op,
            )
        )

    machine_raw = job_raw.get("machine", {})
    post_raw = machine_raw.get("post", {})

    return JobSpec(
        name=job_raw.get("name", "unnamed"),
        part_file=part_raw.get("file", ""),
        unit=part_raw.get("unit", "mm"),
        workpiece_frame=frame,
        features=tuple(features),
        tooling=tuple(job_raw.get("tooling", ())),
        machine_profile=machine_raw.get("profile", "ntx_tcp_provisional"),
        motion_mode=MotionMode(machine_raw.get("kinematics", {}).get("motion_mode", "indexed_3_plus_2")),
        indexed_b_deg=machine_raw.get("kinematics", {}).get("indexed_b_deg"),
        indexed_c_deg=machine_raw.get("kinematics", {}).get("indexed_c_deg"),
        fixture_files=tuple(f.get("file", "") for f in job_raw.get("fixtures", ())),
        stock_file=(job_raw.get("stock", {}) or {}).get("file"),
        feed=float(job_raw.get("process", {}).get("feed", 800.0)),
        safety_lift=float(job_raw.get("process", {}).get("safety_lift", 3.0)),
        lead_in_length=float(job_raw.get("process", {}).get("lead_in_length", 2.0)),
        lead_out_length=float(job_raw.get("process", {}).get("lead_out_length", 2.0)),
        lead_deg=float(job_raw.get("process", {}).get("lead_deg", 0.0)),
        tilt_deg=float(job_raw.get("process", {}).get("tilt_deg", 0.0)),
        coolant=bool(job_raw.get("process", {}).get("coolant", False)),
        program_number=int(post_raw.get("program_number", 1000)),
        work_offset=post_raw.get("work_offset", "G54"),
    )
