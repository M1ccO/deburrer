"""Unit tests for the job schema.

Verifies YAML parsing, schema validation, and round-trip serialization.
"""

from __future__ import annotations

import pytest

from cam_kernel.api.job_schema import (
    CutDirection,
    FeatureOperation,
    FeatureSelection,
    FeatureSelectionType,
    JobSpec,
    MotionMode,
    OperationSpec,
    OperationType,
    WorkpieceFrame,
    job_from_document,
    job_to_document,
    load_job_json,
    load_job_yaml,
    save_job_json,
    validate_job,
)


class TestJobSpec:
    def test_default_job(self):
        job = JobSpec(name="test", part_file="part.step")
        assert job.name == "test"
        assert job.unit == "mm"
        assert job.motion_mode == MotionMode.INDEXED_3_PLUS_2
        assert job.feed == 800.0

    def test_workpiece_frame_default(self):
        frame = WorkpieceFrame()
        assert frame.origin == (0.0, 0.0, 0.0)
        assert frame.spindle_axis == (1.0, 0.0, 0.0)

    def test_feature_operation(self):
        op = FeatureOperation(
            type=OperationType.CHAMFER,
            width=0.5,
            tool_id="chamfer_6mm",
        )
        assert op.width == 0.5
        assert op.type == OperationType.CHAMFER
        assert op.type.value == "chamfer"

    def test_motion_modes(self):
        assert MotionMode.INDEXED_3_PLUS_2.value == "indexed_3_plus_2"
        assert MotionMode.SIMULTANEOUS_5_AXIS.value == "simultaneous_5_axis"

    def test_repository_yaml_layout_loads_all_root_sections(self):
        job = load_job_yaml(
            "jobs/ntx2500_demo_edge_deburr.yaml"
        )

        assert job.name == "ntx2500_demo_edge_deburr"
        assert job.part_file == "parts/demo_part.step"
        assert len(job.features) == 1
        assert len(job.tooling) == 2
        assert len(job.operations) == 1
        assert job.operations[0].feature_label == "Top cover edges"
        assert validate_job(job).ok

    def test_versioned_job_roundtrip_preserves_ordered_operations(self):
        job = JobSpec(
            name="two operations",
            part_file="part.step",
            features=(
                FeatureSelection(
                    type=FeatureSelectionType.EDGE_CHAINS,
                    label="outer",
                    edge_ids=("edge_1",),
                ),
            ),
            tooling=(
                {
                    "id": "ball_3",
                    "kind": "ball",
                    "diameter": 3.0,
                    "stickout": 20.0,
                },
            ),
            operations=(
                OperationSpec(
                    id="deburr",
                    name="Deburr",
                    feature_label="outer",
                    type=OperationType.BALL_DEBURR,
                    tool_id="ball_3",
                    ball_engagement=0.15,
                    cut_direction=CutDirection.REVERSE,
                ),
                OperationSpec(
                    id="spring",
                    name="Spring",
                    feature_label="outer",
                    type=OperationType.BALL_DEBURR,
                    tool_id="ball_3",
                    ball_engagement=0.08,
                    spring_passes=1,
                ),
            ),
        )

        document = job_to_document(job)
        decoded = job_from_document(document)

        assert document["schema"] == "cam_kernel.job"
        assert document["schema_version"] == 1
        assert decoded == job
        assert [operation.id for operation in decoded.operations] == [
            "deburr",
            "spring",
        ]

    def test_job_save_load_json_is_validated(self, tmp_path):
        job = JobSpec(name="empty plan", part_file="part.step")
        path = tmp_path / "job.json"

        save_job_json(path, job)
        decoded = load_job_json(path)

        assert decoded == job

    def test_job_validation_rejects_unknown_references(self):
        job = JobSpec(
            name="bad references",
            part_file="part.step",
            operations=(
                OperationSpec(
                    id="bad",
                    name="Bad",
                    feature_label="missing",
                    type=OperationType.BALL_DEBURR,
                    tool_id="missing",
                    ball_engagement=0.1,
                ),
            ),
        )

        report = validate_job(job)

        assert not report.ok
        assert {issue.code for issue in report.issues} >= {
            "operation.feature",
            "operation.tool",
        }
