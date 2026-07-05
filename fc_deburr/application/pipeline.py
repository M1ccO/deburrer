from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace
from typing import Optional

from ..domain.errors import GeometryError, ValidationError
from ..domain.models import (
    FeatureLoop,
    MachineToolpath,
    MotionMode,
    Operation,
    ToolDefinition,
    ToolKind,
    Toolpath,
    ValidationReport,
    operation_motion_mode,
)
from ..kernel.adapters import (
    contact_intent_from_operation,
    selected_sequence_to_toolpath,
    tool_assembly_from_definition,
    toolpath_to_candidate_graph,
)
from ..kernel.feasibility import (
    FeasibilityBackend,
    NoOpFeasibilityBackend,
    evaluate_graph,
)
from ..kernel.models import (
    KernelDiagnostic,
    SelectionWeights,
)
from ..kernel.selection import NoFeasibleSequenceError, select_sequence
from ..machine.backends import (
    LegacyNtxKinematicsBackend,
    MachineKinematicsBackend,
)
from ..machine.profiles import MachineProfile
from ..machine.validation import validate_feature, validate_machine_path
from ..features.wire import prepare_wire_loop
from ..solver.ball import solve_ball_cut
from ..solver.chamfer import solve_chamfer_cut
from ..solver.motion import add_approach_and_retract
from ..solver.posture import realize_motion_mode
from ..solver.transforms import apply_spring_passes


@dataclass(frozen=True)
class PipelineResult:
    model_path: Toolpath
    machine_path: MachineToolpath
    validation: ValidationReport
    side_auto_picked: bool = False
    side_used: bool = False
    kernel_diagnostics: tuple[KernelDiagnostic, ...] = ()
    selection_total_cost: float = 0.0
    indexed_b_deg: float | None = None
    indexed_c_deg: float | None = None


def _b_limit_severity(report: ValidationReport) -> int:
    return sum(1 for issue in report.issues if issue.code == "machine.b_limit")


def _format_blocking_issues(
    report: ValidationReport,
    limit: int = 6,
) -> str:
    blocking = [issue for issue in report.issues if issue.is_error]
    rendered = []
    for issue in blocking[:limit]:
        sample = (
            " (sample %d)" % issue.sample_index
            if issue.sample_index is not None
            else ""
        )
        rendered.append(issue.message + sample)
    remaining = len(blocking) - len(rendered)
    if remaining > 0:
        rendered.append("%d additional issue(s)" % remaining)
    return "; ".join(rendered)


def _try_side(
    loop: FeatureLoop,
    tool: ToolDefinition,
    operation: Operation,
    machine_profile: MachineProfile,
    feasibility_backend: FeasibilityBackend,
    kinematics_backend: MachineKinematicsBackend,
    selection_weights: SelectionWeights,
) -> PipelineResult:
    mode = operation_motion_mode(operation)
    spherical_indexed = (
        tool.kind is ToolKind.BALL
        and mode is MotionMode.INDEXED_3_PLUS_2
    )
    if spherical_indexed:
        operation = dc_replace(
            operation,
            lead_deg=0.0,
            tilt_deg=0.0,
        )
    prepared_loop = prepare_wire_loop(
        loop,
        operation,
        subdivide_for_posture=not spherical_indexed,
    )
    feature_report = validate_feature(
        prepared_loop,
        machine_profile,
        discontinuities_are_warnings=spherical_indexed,
    )
    if not feature_report.ok:
        raise ValidationError(
            "Invalid feature for %s/%s: %s"
            % (
                tool.kind.value,
                mode.value,
                _format_blocking_issues(feature_report),
            )
        )

    if tool.kind is ToolKind.CHAMFER:
        analytic_path = solve_chamfer_cut(prepared_loop, tool, operation)
    elif tool.kind is ToolKind.BALL:
        analytic_path = solve_ball_cut(prepared_loop, tool, operation)
    else:
        raise ValidationError("Unsupported tool kind: %s" % tool.kind)

    # For a spherical cutter, contact geometry is independent of spindle
    # orientation. Realize the fixed indexed posture before machine
    # feasibility so varying local bisectors are preferences, not false
    # per-station B/C requirements.
    pre_realized = (
        realize_motion_mode(
            analytic_path,
            tool,
            operation,
            machine_profile,
        )
        if spherical_indexed
        else None
    )
    candidate_path = (
        pre_realized.path if pre_realized is not None else analytic_path
    )

    intent = contact_intent_from_operation(
        prepared_loop.id, tool, operation
    )
    assembly = tool_assembly_from_definition(tool)
    candidate_graph = toolpath_to_candidate_graph(candidate_path, intent)
    candidate_graph, diagnostics = evaluate_graph(
        candidate_graph, intent, assembly, feasibility_backend
    )
    machine_graph = kinematics_backend.expand(
        candidate_graph,
        machine_profile,
        mode,
    )
    try:
        selected = select_sequence(machine_graph, selection_weights)
    except NoFeasibleSequenceError as error:
        raise ValidationError(str(error)) from error

    selected_path = selected_sequence_to_toolpath(
        selected, candidate_path
    )
    realized = (
        dc_replace(pre_realized, path=selected_path)
        if pre_realized is not None
        else realize_motion_mode(
            selected_path, tool, operation, machine_profile
        )
    )
    cut_path = realized.path
    model_path = add_approach_and_retract(cut_path, operation)
    model_path = apply_spring_passes(model_path, operation)
    machine_path = kinematics_backend.solve_path(
        model_path,
        machine_profile,
        mode,
        realized.indexed_b_deg,
        realized.indexed_c_deg,
    )
    machine_report = validate_machine_path(machine_path, machine_profile)
    diagnostics = diagnostics + (
        KernelDiagnostic(
            code="selection.complete",
            message="Selected %d posture candidates" % len(
                selected.candidates
            ),
        ),
    )
    return PipelineResult(
        model_path=model_path,
        machine_path=machine_path,
        validation=ValidationReport(
            feature_report.issues + machine_report.issues
        ),
        side_auto_picked=False,
        side_used=bool(operation.flip_side),
        kernel_diagnostics=diagnostics,
        selection_total_cost=selected.total_cost,
        indexed_b_deg=realized.indexed_b_deg,
        indexed_c_deg=realized.indexed_c_deg,
    )


def calculate_toolpath(
    loop: FeatureLoop,
    tool: ToolDefinition,
    operation: Operation,
    machine_profile: MachineProfile,
    feasibility_backend: Optional[FeasibilityBackend] = None,
    kinematics_backend: Optional[MachineKinematicsBackend] = None,
    selection_weights: SelectionWeights = SelectionWeights(),
) -> PipelineResult:
    """Solve a wire-deburr toolpath.

    The engine tries the requested side first, and if the B-axis goes out of
    range it falls back to the opposite side automatically.  This keeps the
    operator's ``flip_side`` choice as the primary intent, but removes the
    ergonomic trap where the same wire works on one side and not the other
    because of the model-to-machine mapping direction.
    """
    feasibility_backend = (
        feasibility_backend or NoOpFeasibilityBackend()
    )
    kinematics_backend = (
        kinematics_backend or LegacyNtxKinematicsBackend()
    )
    user_side = bool(operation.flip_side)
    primary_error = None
    try:
        primary = _try_side(
            loop,
            tool,
            operation,
            machine_profile,
            feasibility_backend,
            kinematics_backend,
            selection_weights,
        )
    except (ValidationError, GeometryError) as error:
        primary = None
        primary_error = error

    if primary is not None and primary.validation.ok:
        return dc_replace(
            primary,
            side_auto_picked=False,
            side_used=user_side,
        )

    alt_operation = dc_replace(operation, flip_side=not user_side)
    alt_error = None
    try:
        alt = _try_side(
            loop,
            tool,
            alt_operation,
            machine_profile,
            feasibility_backend,
            kinematics_backend,
            selection_weights,
        )
    except (ValidationError, GeometryError) as error:
        alt = None
        alt_error = error

    if primary is None and alt is None:
        if str(primary_error) == str(alt_error):
            raise ValidationError(
                "No feasible %s posture: %s"
                % (
                    operation_motion_mode(operation).value,
                    primary_error or "failed",
                )
            )
        raise ValidationError(
            "No feasible %s posture. Requested side: %s. "
            "Opposite side: %s"
            % (
                operation_motion_mode(operation).value,
                primary_error or "failed",
                alt_error or "failed",
            )
        )
    if alt is not None and alt.validation.ok and (
        primary is None
        or not primary.validation.ok
        or _b_limit_severity(alt.validation)
        < _b_limit_severity(primary.validation)
    ):
        return dc_replace(
            alt,
            side_auto_picked=(not user_side),
            side_used=not user_side,
        )

    chosen = primary if primary is not None else alt
    if chosen is None:
        raise ValidationError("Invalid feature: no valid side found")
    if not chosen.validation.ok:
        raise ValidationError(
            "Invalid machine path: "
            + _format_blocking_issues(chosen.validation)
        )
    return chosen
