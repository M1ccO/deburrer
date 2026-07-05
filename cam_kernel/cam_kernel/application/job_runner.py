"""Execute ordered B-Rep edge operations from a versioned CAM job."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from ..api.job_schema import (
    FeatureSelectionType,
    JobSpec,
    OperationSpec,
    OperationType,
    validate_job,
)
from ..geometry.feature_extract import (
    sample_selected_edges_from_shape,
)
from ..geometry.occt_session import OcctSession
from fc_deburr.application.job_metrics import JobMetrics, estimate_job
from fc_deburr.application.pipeline import PipelineResult, calculate_toolpath
from fc_deburr.domain.models import (
    CutDirection,
    FeatureLoop,
    FeatureSample,
    MotionMode,
    Operation,
    ToolDefinition,
    ToolKind,
)
from fc_deburr.machine.profiles import (
    MachineProfile,
    WorkpieceFrame,
)


@dataclass(frozen=True)
class OperationExecution:
    operation: OperationSpec
    feature: FeatureLoop
    tool: ToolDefinition
    result: PipelineResult
    metrics: JobMetrics


@dataclass(frozen=True)
class JobExecution:
    job: JobSpec
    operations: Tuple[OperationExecution, ...]

    @property
    def machine_point_count(self) -> int:
        return sum(
            len(operation.result.machine_path.points)
            for operation in self.operations
        )


def run_job(
    job: JobSpec,
    base_directory: str | Path | None = None,
) -> JobExecution:
    """Run enabled edge-deburr operations in persisted job order.

    Face-finishing operations remain on their existing OCCT web pipeline and
    are rejected here until that strategy is moved behind the same reusable
    application contract.
    """
    report = validate_job(job)
    if not report.ok:
        raise ValueError(
            "Invalid CAM job: "
            + "; ".join(
                issue.message
                for issue in report.issues
                if issue.level.value == "error"
            )
        )
    if job.machine_profile != "ntx_tcp_provisional":
        raise ValueError(
            "Unsupported machine profile: %s" % job.machine_profile
        )

    root = Path(base_directory) if base_directory is not None else Path.cwd()
    part_path = Path(job.part_file)
    if not part_path.is_absolute():
        part_path = root / part_path
    if not part_path.is_file():
        raise ValueError("STEP part file does not exist: %s" % part_path)

    feature_specs = {
        feature.label: feature for feature in job.features
    }
    tools = {
        str(tool["id"]): _tool_from_mapping(tool)
        for tool in job.tooling
    }
    profile = MachineProfile(
        id=job.machine_profile,
        workpiece=WorkpieceFrame(
            origin_xyz=tuple(job.workpiece_frame.origin),
            spindle_axis=tuple(job.workpiece_frame.spindle_axis),
        ),
    )

    completed = []
    with OcctSession() as session:
        shape = session.load_step(str(part_path))
        feature_cache = {}
        for operation_spec in job.operations:
            if not operation_spec.enabled:
                continue
            feature_spec = feature_specs[operation_spec.feature_label]
            if feature_spec.type is not FeatureSelectionType.EDGE_CHAINS:
                raise ValueError(
                    "Operation %s uses a face region; the reusable job runner "
                    "currently supports edge chains only"
                    % operation_spec.id
                )
            if operation_spec.type is OperationType.FACE_FINISHING:
                raise ValueError(
                    "Face finishing is not yet available in the reusable job runner"
                )
            if operation_spec.feature_label not in feature_cache:
                samples = sample_selected_edges_from_shape(
                    shape,
                    feature_spec.edge_ids,
                    spacing=feature_spec.sampling_spacing,
                )
                feature_cache[operation_spec.feature_label] = FeatureLoop(
                    id=operation_spec.feature_label,
                    samples=tuple(
                        FeatureSample(
                            position=sample.position,
                            tangent=sample.tangent,
                            guide_normal=sample.guide_normal,
                            other_normal=sample.other_normal,
                            source_edge_id=sample.edge_id,
                        )
                        for sample in samples.samples
                    ),
                    closed=samples.closed,
                    center_xyz=samples.center_xyz,
                    source_object_id=str(part_path),
                    source_edge_ids=tuple(feature_spec.edge_ids),
                )

            feature = feature_cache[operation_spec.feature_label]
            tool = tools[operation_spec.tool_id]
            operation = _domain_operation(operation_spec)
            result = calculate_toolpath(
                feature,
                tool,
                operation,
                profile,
            )
            metrics = estimate_job(
                feature,
                result.machine_path,
                profile,
                model_path=result.model_path,
            )
            completed.append(
                OperationExecution(
                    operation_spec,
                    feature,
                    tool,
                    result,
                    metrics,
                )
            )

    return JobExecution(job, tuple(completed))


def _tool_from_mapping(raw: dict) -> ToolDefinition:
    kind = ToolKind(str(raw.get("kind", "")))
    return ToolDefinition(
        id=str(raw["id"]),
        kind=kind,
        diameter=float(raw["diameter"]),
        stickout=float(raw["stickout"]),
        cutting_length=float(raw.get("cutting_length", 0.0)),
        included_angle_deg=_optional_float(
            raw.get("included_angle_deg")
        ),
        tip_flat_diameter=float(raw.get("tip_flat_diameter", 0.0)),
        tip_radius=float(raw.get("tip_radius", 0.0)),
        contact_radius=_optional_float(raw.get("contact_radius")),
        radial_correction=float(raw.get("radial_correction", 0.0)),
        axial_correction=float(raw.get("axial_correction", 0.0)),
    )


def _domain_operation(spec: OperationSpec) -> Operation:
    return Operation(
        id=spec.id,
        tool_id=spec.tool_id,
        target_width=spec.width,
        ball_break_width=spec.ball_break_width,
        ball_engagement=spec.ball_engagement,
        feed=spec.feed,
        lead_deg=spec.lead_deg,
        tilt_deg=spec.tilt_deg,
        lead_in_length=spec.lead_in_length,
        lead_out_length=spec.lead_out_length,
        safety_lift=spec.safety_lift,
        motion_mode=MotionMode(spec.motion_mode.value),
        auto_index=(
            spec.indexed_b_deg is None or spec.indexed_c_deg is None
        ),
        indexed_b_deg=spec.indexed_b_deg,
        indexed_c_deg=spec.indexed_c_deg,
        cut_direction=CutDirection(spec.cut_direction.value),
        spring_passes=spec.spring_passes,
        spring_feed_fraction=spec.spring_feed_fraction,
    )


def _optional_float(value):
    if value is None or value == "":
        return None
    return float(value)
