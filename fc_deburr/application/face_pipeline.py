from ..domain.errors import ValidationError
from ..domain.models import (
    FaceRegion,
    Operation,
    ToolDefinition,
    operation_motion_mode,
)
from ..freecad_adapter.face_finishing import solve_face_finish
from ..machine.backends import (
    LegacyNtxKinematicsBackend,
    MachineKinematicsBackend,
)
from ..machine.profiles import MachineProfile
from ..machine.validation import validate_machine_path
from ..solver.posture import realize_motion_mode
from .pipeline import PipelineResult


def calculate_face_toolpath(
    region: FaceRegion,
    tool: ToolDefinition,
    operation: Operation,
    machine_profile: MachineProfile,
    kinematics_backend: MachineKinematicsBackend | None = None,
) -> PipelineResult:
    kinematics_backend = (
        kinematics_backend or LegacyNtxKinematicsBackend()
    )
    analytic_path = solve_face_finish(region, tool, operation)
    realized = realize_motion_mode(
        analytic_path, tool, operation, machine_profile
    )
    model_path = realized.path
    machine_path = kinematics_backend.solve_path(
        model_path,
        machine_profile,
        operation_motion_mode(operation),
        realized.indexed_b_deg,
        realized.indexed_c_deg,
    )
    report = validate_machine_path(machine_path, machine_profile)
    if not report.ok:
        raise ValidationError(
            "Invalid machine path: "
            + "; ".join(issue.message for issue in report.issues)
        )
    return PipelineResult(
        model_path,
        machine_path,
        report,
        indexed_b_deg=realized.indexed_b_deg,
        indexed_c_deg=realized.indexed_c_deg,
    )
