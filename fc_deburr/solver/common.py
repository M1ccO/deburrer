from __future__ import annotations

from ..domain.errors import GeometryError
from ..domain.models import FeatureLoop, ToolDefinition


def validate_common_inputs(loop: FeatureLoop, tool: ToolDefinition) -> None:
    if loop.closed and len(loop.samples) < 3:
        raise GeometryError("A closed feature loop requires at least three samples")
    if not loop.closed and len(loop.samples) < 2:
        raise GeometryError("An open feature path requires at least two samples")
    if tool.diameter <= 0.0:
        raise GeometryError("Tool diameter must be positive")
    if tool.stickout <= 0.0:
        raise GeometryError("Tool stickout must be positive")
