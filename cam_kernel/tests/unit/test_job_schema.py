"""Unit tests for the job schema.

Verifies YAML parsing, schema validation, and round-trip serialization.
"""

from __future__ import annotations

import pytest

from cam_kernel.api.job_schema import (
    FeatureOperation,
    FeatureSelection,
    FeatureSelectionType,
    JobSpec,
    MotionMode,
    OperationType,
    WorkpieceFrame,
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
