"""Geometry-aware deburring engine.

The package deliberately keeps FreeCAD, solving, machine kinematics, and NC
rendering behind separate module boundaries.  Domain values are immutable and
may be passed between layers without transferring mutable ownership.
"""

from .domain.models import (
    FeatureLoop,
    FeatureSample,
    MotionKind,
    MotionMode,
    Operation,
    PathPoint,
    ToolDefinition,
    ToolKind,
    Toolpath,
)

__all__ = [
    "FeatureLoop",
    "FeatureSample",
    "MotionKind",
    "MotionMode",
    "Operation",
    "PathPoint",
    "ToolDefinition",
    "ToolKind",
    "Toolpath",
]
