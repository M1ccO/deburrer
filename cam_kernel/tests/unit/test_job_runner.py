from pathlib import Path

from cam_kernel.api.job_schema import (
    FeatureSelection,
    FeatureSelectionType,
    JobSpec,
    OperationSpec,
    OperationType,
)
from cam_kernel.application.job_runner import run_job
from cam_kernel.geometry.occt_session import OcctSession
from cam_kernel.geometry.feature_extract import topology_selection_payload


def test_job_runner_executes_enabled_edge_operations_in_order():
    part = Path(
        "cam_kernel/tests/geometry_regression/parts/box.step"
    ).resolve()
    with OcctSession() as session:
        shape = session.load_step(str(part))
        edge_id = topology_selection_payload(shape)["edges"][0]["id"]

    job = JobSpec(
        name="ordered edge job",
        part_file=str(part),
        features=(
            FeatureSelection(
                type=FeatureSelectionType.EDGE_CHAINS,
                label="edge",
                edge_ids=(edge_id,),
                sampling_spacing=1.0,
            ),
        ),
        tooling=(
            {
                "id": "ball_3",
                "kind": "ball",
                "diameter": 3.0,
                "stickout": 20.0,
                "cutting_length": 8.0,
                "tip_radius": 1.5,
            },
        ),
        operations=(
            OperationSpec(
                id="first",
                name="First",
                feature_label="edge",
                type=OperationType.BALL_DEBURR,
                tool_id="ball_3",
                ball_engagement=0.15,
            ),
            OperationSpec(
                id="disabled",
                name="Disabled",
                feature_label="edge",
                type=OperationType.BALL_DEBURR,
                tool_id="ball_3",
                ball_engagement=0.10,
                enabled=False,
            ),
            OperationSpec(
                id="spring",
                name="Spring",
                feature_label="edge",
                type=OperationType.BALL_DEBURR,
                tool_id="ball_3",
                ball_engagement=0.08,
                spring_passes=1,
            ),
        ),
    )

    execution = run_job(job)

    assert [
        operation.operation.id for operation in execution.operations
    ] == ["first", "spring"]
    assert execution.machine_point_count > 0
    assert len(execution.operations[1].result.model_path.points) == (
        len(execution.operations[0].result.model_path.points) * 2
    )
