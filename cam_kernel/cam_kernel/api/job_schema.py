"""Job schema — the top-level CAM job description.

A job binds a part, feature selections, tooling, machine profile, fixtures,
stock, and process parameters into a single serializable document.  The kernel
reads a job, solves the requested operations, and emits validated machine
toolpaths and NC output.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple


SCHEMA_ID = "cam_kernel.job"
SCHEMA_VERSION = 1


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


class CutDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


class CoolantMode(str, Enum):
    NONE = "none"
    MIST = "mist"
    FLOOD = "flood"
    MIST_FLOOD = "mist_flood"
    THROUGH = "through"


class IssueLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"


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
    ball_break_width: Optional[float] = None
    ball_engagement: Optional[float] = None
    tool_id: str = ""


@dataclass(frozen=True)
class OperationSpec:
    """One ordered operation in a persistent CAM job."""

    id: str
    name: str
    feature_label: str
    type: OperationType
    tool_id: str
    enabled: bool = True
    motion_mode: MotionMode = MotionMode.INDEXED_3_PLUS_2
    width: Optional[float] = None
    ball_break_width: Optional[float] = None
    ball_engagement: Optional[float] = None
    feed: float = 800.0
    plunge_feed: Optional[float] = None
    spindle_rpm: Optional[int] = None
    coolant: CoolantMode = CoolantMode.NONE
    safety_lift: float = 3.0
    lead_in_length: float = 2.0
    lead_out_length: float = 2.0
    lead_deg: float = 0.0
    tilt_deg: float = 0.0
    cut_direction: CutDirection = CutDirection.FORWARD
    spring_passes: int = 0
    spring_feed_fraction: float = 0.5
    indexed_b_deg: Optional[float] = None
    indexed_c_deg: Optional[float] = None
    parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class JobIssue:
    level: IssueLevel
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class JobValidationReport:
    issues: Tuple[JobIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(
            issue.level is IssueLevel.ERROR for issue in self.issues
        )


@dataclass(frozen=True)
class JobSpec:
    name: str
    part_file: str
    unit: str = "mm"
    workpiece_frame: WorkpieceFrame = field(default_factory=WorkpieceFrame)
    features: Tuple[FeatureSelection, ...] = ()
    tooling: Tuple[dict, ...] = ()
    operations: Tuple[OperationSpec, ...] = ()
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
    """Parse either supported YAML layout into a validated ``JobSpec``."""
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    job = job_from_mapping(raw)
    _raise_for_invalid_job(job)
    return job


def load_job_json(path: str | Path) -> JobSpec:
    with open(path, encoding="utf-8") as stream:
        document = json.load(stream)
    job = job_from_document(document)
    _raise_for_invalid_job(job)
    return job


def load_job(path: str | Path) -> JobSpec:
    suffix = Path(path).suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_job_yaml(str(path))
    if suffix == ".json":
        return load_job_json(path)
    raise ValueError("CAM jobs must use .json, .yaml, or .yml")


def save_job_json(path: str | Path, job: JobSpec) -> None:
    """Atomically save a complete, versioned CAM job document."""
    _raise_for_invalid_job(job)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(job_to_document(job), stream, indent=2)
        stream.write("\n")
    os.replace(temporary, target)


def job_to_document(job: JobSpec) -> dict:
    features = []
    for feature in job.features:
        feature_data = {
            "type": feature.type.value,
            "label": feature.label,
            "selection": {
                "edge_ids": list(feature.edge_ids),
                "face_ids": list(feature.face_ids),
            },
            "sampling": {"spacing": feature.sampling_spacing},
        }
        if feature.operation is not None:
            feature_data["operation"] = _json_value(
                asdict(feature.operation)
            )
        features.append(feature_data)
    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "job": {
            "name": job.name,
            "part": {
                "file": job.part_file,
                "unit": job.unit,
                "workpiece_frame": {
                    "origin": list(job.workpiece_frame.origin),
                    "spindle_axis": list(
                        job.workpiece_frame.spindle_axis
                    ),
                },
            },
            "features": features,
            "tooling": _json_value(list(job.tooling)),
            "operations": _json_value(
                [asdict(operation) for operation in job.operations]
            ),
            "machine": {
                "profile": job.machine_profile,
                "kinematics": {
                    "motion_mode": job.motion_mode.value,
                    "indexed_b_deg": job.indexed_b_deg,
                    "indexed_c_deg": job.indexed_c_deg,
                },
                "post": {
                    "program_number": job.program_number,
                    "work_offset": job.work_offset,
                },
            },
            "fixtures": [
                {"file": path} for path in job.fixture_files
            ],
            "stock": (
                {"file": job.stock_file}
                if job.stock_file is not None
                else {}
            ),
            "process": {
                "feed": job.feed,
                "safety_lift": job.safety_lift,
                "lead_in_length": job.lead_in_length,
                "lead_out_length": job.lead_out_length,
                "lead_deg": job.lead_deg,
                "tilt_deg": job.tilt_deg,
                "coolant": job.coolant,
            },
        },
    }


def job_from_document(document: dict) -> JobSpec:
    if document.get("schema") != SCHEMA_ID:
        raise ValueError("Not a cam_kernel job document")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported cam_kernel job schema version")
    payload = document.get("job")
    if not isinstance(payload, dict):
        raise ValueError("Missing job object")
    return job_from_mapping(payload)


def job_from_mapping(raw: dict) -> JobSpec:
    if not isinstance(raw, dict):
        raise ValueError("CAM job root must be an object")

    job_raw = _normalize_job_root(raw)
    part_raw = job_raw.get("part", {})
    if not isinstance(part_raw, dict):
        part_raw = {}

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
                ball_break_width=op_raw.get("ball_break_width"),
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
    if not isinstance(machine_raw, dict):
        machine_raw = {}
    post_raw = machine_raw.get("post", {})
    if not isinstance(post_raw, dict):
        post_raw = {}
    process_raw = job_raw.get("process", {})
    if not isinstance(process_raw, dict):
        process_raw = {}
    default_motion_mode = MotionMode(
        machine_raw.get("kinematics", {}).get(
            "motion_mode",
            "indexed_3_plus_2",
        )
    )
    operations = tuple(
        _operation_from_mapping(
            item,
            default_motion_mode=default_motion_mode,
            default_feed=float(process_raw.get("feed", 800.0)),
            default_safety_lift=float(
                process_raw.get("safety_lift", 3.0)
            ),
        )
        for item in job_raw.get("operations", ())
    )
    if not operations:
        operations = _legacy_operations_from_features(
            features,
            default_motion_mode,
            process_raw,
        )

    return JobSpec(
        name=job_raw.get("name", "unnamed"),
        part_file=part_raw.get("file", ""),
        unit=part_raw.get("unit", "mm"),
        workpiece_frame=frame,
        features=tuple(features),
        tooling=tuple(job_raw.get("tooling", ())),
        operations=operations,
        machine_profile=machine_raw.get("profile", "ntx_tcp_provisional"),
        motion_mode=default_motion_mode,
        indexed_b_deg=machine_raw.get("kinematics", {}).get("indexed_b_deg"),
        indexed_c_deg=machine_raw.get("kinematics", {}).get("indexed_c_deg"),
        fixture_files=tuple(f.get("file", "") for f in job_raw.get("fixtures", ())),
        stock_file=(job_raw.get("stock", {}) or {}).get("file"),
        feed=float(process_raw.get("feed", 800.0)),
        safety_lift=float(process_raw.get("safety_lift", 3.0)),
        lead_in_length=float(process_raw.get("lead_in_length", 2.0)),
        lead_out_length=float(process_raw.get("lead_out_length", 2.0)),
        lead_deg=float(process_raw.get("lead_deg", 0.0)),
        tilt_deg=float(process_raw.get("tilt_deg", 0.0)),
        coolant=bool(process_raw.get("coolant", False)),
        program_number=int(post_raw.get("program_number", 1000)),
        work_offset=post_raw.get("work_offset", "G54"),
    )


def validate_job(job: JobSpec) -> JobValidationReport:
    issues = []

    def error(code, message, path=""):
        issues.append(JobIssue(IssueLevel.ERROR, code, message, path))

    def warning(code, message, path=""):
        issues.append(JobIssue(IssueLevel.WARNING, code, message, path))

    if not job.name.strip():
        error("job.name", "Job name cannot be empty", "name")
    if not job.part_file.strip():
        error("job.part_file", "Job requires a STEP part file", "part_file")
    if job.unit != "mm":
        error("job.unit", "Only millimetres are currently supported", "unit")
    if job.feed <= 0.0:
        error("job.feed", "Default feed must be positive", "feed")
    if job.safety_lift <= 0.0:
        error(
            "job.safety_lift",
            "Default safety lift must be positive",
            "safety_lift",
        )
    if not 1 <= job.program_number <= 99999999:
        error(
            "job.program_number",
            "Program number is outside the supported range",
            "program_number",
        )

    feature_labels = [feature.label for feature in job.features]
    _check_unique(
        feature_labels,
        "feature.label",
        "Feature labels must be unique and non-empty",
        issues,
    )
    tool_ids = [str(tool.get("id", "")) for tool in job.tooling]
    _check_unique(
        tool_ids,
        "tool.id",
        "Tool IDs must be unique and non-empty",
        issues,
    )
    operation_ids = [operation.id for operation in job.operations]
    _check_unique(
        operation_ids,
        "operation.id",
        "Operation IDs must be unique and non-empty",
        issues,
    )

    feature_set = set(feature_labels)
    tool_set = set(tool_ids)
    for index, feature in enumerate(job.features):
        if not feature.edge_ids and not feature.face_ids:
            warning(
                "feature.unresolved",
                "Feature has no persisted topology IDs yet",
                "features[%d]" % index,
            )
        if feature.sampling_spacing <= 0.0:
            error(
                "feature.spacing",
                "Feature sampling spacing must be positive",
                "features[%d].sampling_spacing" % index,
            )

    for index, operation in enumerate(job.operations):
        prefix = "operations[%d]" % index
        if operation.feature_label not in feature_set:
            error(
                "operation.feature",
                "Operation references an unknown feature",
                prefix + ".feature_label",
            )
        if operation.tool_id not in tool_set:
            error(
                "operation.tool",
                "Operation references an unknown tool",
                prefix + ".tool_id",
            )
        if operation.feed <= 0.0:
            error(
                "operation.feed",
                "Operation feed must be positive",
                prefix + ".feed",
            )
        if operation.safety_lift <= 0.0:
            error(
                "operation.safety_lift",
                "Operation safety lift must be positive",
                prefix + ".safety_lift",
            )
        if not 0 <= operation.spring_passes <= 10:
            error(
                "operation.spring_passes",
                "Spring pass count must be between 0 and 10",
                prefix + ".spring_passes",
            )
        if not 0.0 < operation.spring_feed_fraction <= 1.0:
            error(
                "operation.spring_feed_fraction",
                "Spring feed fraction must be greater than 0 and at most 1",
                prefix + ".spring_feed_fraction",
            )
        if operation.type is OperationType.CHAMFER and (
            operation.width is None or operation.width <= 0.0
        ):
            error(
                "operation.width",
                "Chamfer operation requires a positive width",
                prefix + ".width",
            )
        if operation.type is OperationType.BALL_DEBURR and not (
            (
                operation.ball_break_width is not None
                and operation.ball_break_width > 0.0
            )
            or (
                operation.ball_engagement is not None
                and operation.ball_engagement > 0.0
            )
        ):
            error(
                "operation.ball_engagement",
                "Ball deburr operation requires a positive rounded-break "
                "width (or legacy center engagement)",
                prefix + ".ball_break_width",
            )

    return JobValidationReport(tuple(issues))


def _normalize_job_root(raw: dict) -> dict:
    metadata = raw.get("job")
    if not isinstance(metadata, dict):
        return raw
    # Historical YAML kept only name under ``job:`` and all real sections at
    # the root. New documents put the complete payload under ``job``.
    siblings = {
        key: value
        for key, value in raw.items()
        if key not in ("job", "schema", "schema_version")
    }
    return {**siblings, **metadata}


def _operation_from_mapping(
    raw: dict,
    default_motion_mode: MotionMode,
    default_feed: float,
    default_safety_lift: float,
) -> OperationSpec:
    if not isinstance(raw, dict):
        raise ValueError("Each operation must be an object")
    parameters = raw.get("parameters", raw.get("params", {}))
    if not isinstance(parameters, dict):
        parameters = {}
    operation_type = OperationType(raw.get("type", "ball_deburr"))
    operation_id = str(raw.get("id", "")).strip()
    name = str(raw.get("name", operation_id or operation_type.value))
    return OperationSpec(
        id=operation_id or _slug(name),
        name=name,
        feature_label=str(
            raw.get("feature_label", raw.get("feature", ""))
        ),
        type=operation_type,
        tool_id=str(raw.get("tool_id", "")),
        enabled=bool(raw.get("enabled", True)),
        motion_mode=MotionMode(
            raw.get("motion_mode", default_motion_mode.value)
        ),
        width=_optional_float(raw.get("width")),
        ball_break_width=_optional_float(
            raw.get("ball_break_width")
        ),
        ball_engagement=_optional_float(raw.get("ball_engagement")),
        feed=float(raw.get("feed", default_feed)),
        plunge_feed=_optional_float(raw.get("plunge_feed")),
        spindle_rpm=_optional_int(raw.get("spindle_rpm")),
        coolant=CoolantMode(raw.get("coolant", "none")),
        safety_lift=float(
            raw.get("safety_lift", default_safety_lift)
        ),
        lead_in_length=float(raw.get("lead_in_length", 2.0)),
        lead_out_length=float(raw.get("lead_out_length", 2.0)),
        lead_deg=float(raw.get("lead_deg", 0.0)),
        tilt_deg=float(raw.get("tilt_deg", 0.0)),
        cut_direction=CutDirection(
            raw.get("cut_direction", "forward")
        ),
        spring_passes=int(raw.get("spring_passes", 0)),
        spring_feed_fraction=float(
            raw.get("spring_feed_fraction", 0.5)
        ),
        indexed_b_deg=_optional_float(raw.get("indexed_b_deg")),
        indexed_c_deg=_optional_float(raw.get("indexed_c_deg")),
        parameters=dict(parameters),
    )


def _legacy_operations_from_features(
    features,
    default_motion_mode,
    process_raw,
):
    operations = []
    for index, feature in enumerate(features):
        legacy = feature.operation
        if legacy is None:
            continue
        operation_id = _slug(feature.label) or "operation_%d" % index
        operations.append(
            OperationSpec(
                id=operation_id,
                name=feature.label or operation_id,
                feature_label=feature.label,
                type=legacy.type,
                tool_id=legacy.tool_id,
                motion_mode=default_motion_mode,
                width=legacy.width,
                ball_break_width=legacy.ball_break_width,
                ball_engagement=legacy.ball_engagement,
                feed=float(process_raw.get("feed", 800.0)),
                safety_lift=float(
                    process_raw.get("safety_lift", 3.0)
                ),
                lead_in_length=float(
                    process_raw.get("lead_in_length", 2.0)
                ),
                lead_out_length=float(
                    process_raw.get("lead_out_length", 2.0)
                ),
                lead_deg=float(process_raw.get("lead_deg", 0.0)),
                tilt_deg=float(process_raw.get("tilt_deg", 0.0)),
                coolant=(
                    CoolantMode.FLOOD
                    if process_raw.get("coolant", False)
                    else CoolantMode.NONE
                ),
            )
        )
    return tuple(operations)


def _check_unique(values, code, message, issues):
    seen = set()
    for index, value in enumerate(values):
        if not value or value in seen:
            issues.append(
                JobIssue(
                    IssueLevel.ERROR,
                    code,
                    message,
                    "%s[%d]" % (code, index),
                )
            )
        seen.add(value)


def _raise_for_invalid_job(job):
    report = validate_job(job)
    if report.ok:
        return
    raise ValueError(
        "Invalid CAM job: "
        + "; ".join(
            issue.message
            for issue in report.issues
            if issue.level is IssueLevel.ERROR
        )
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_value(item) for key, item in value.items()
        }
    return value


def _optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value):
    if value is None or value == "":
        return None
    return int(value)


def _slug(value):
    text = "".join(
        character.lower() if character.isalnum() else "_"
        for character in str(value)
    )
    return "_".join(part for part in text.split("_") if part)
