"""Unit tests for cutter models and engagement rules."""

from __future__ import annotations

import math
import pytest

from cam_kernel.tools.cutter_models import (
    ball_center_from_contact,
    chamfer_cone_slope_deg,
    chamfer_tangency_check,
    CutterParams,
    CutterKind,
)
from cam_kernel.tools.engagement_rules import (
    ball_effective_radius,
    chamfer_max_width,
    face_stepover,
)


class TestBallModel:
    def test_ball_center_from_contact(self):
        contact = (0.0, 0.0, 0.0)
        axis = (0.0, 0.0, 1.0)
        radius = 5.0
        center = ball_center_from_contact(contact, axis, radius)
        assert center == (0.0, 0.0, 5.0)

    def test_ball_center_non_unit_axis(self):
        contact = (1.0, 2.0, 3.0)
        axis = (3.0, 0.0, 0.0)
        radius = 2.0
        center = ball_center_from_contact(contact, axis, radius)
        from fc_deburr.geometry.vectors import length

        assert abs(length((center[0] - 1.0, center[1] - 2.0, center[2] - 3.0)) - radius) < 1e-10


class TestChamferModel:
    def test_chamfer_cone_slope(self):
        slope = chamfer_cone_slope_deg(90.0)
        assert abs(slope - 45.0) < 1e-10

    def test_chamfer_tangency(self):
        tool_axis = (0.0, 0.0, 1.0)
        cone_normal = (0.0, 0.0, 1.0)
        slope = 0.0
        assert chamfer_tangency_check(tool_axis, cone_normal, slope)


class TestEngagementRules:
    def test_ball_effective_radius(self):
        r = ball_effective_radius(5.0, 1.0)
        expected = math.sqrt(5.0**2 - 4.0**2)
        assert abs(r - expected) < 1e-10

    def test_chamfer_max_width(self):
        width = chamfer_max_width(90.0, 3.0)
        expected = 3.0 * math.cos(math.radians(45.0))
        assert abs(width - expected) < 1e-10

    def test_face_stepover(self):
        s = face_stepover(5.0, 0.01)
        expected = 2.0 * math.sqrt(2 * 5.0 * 0.01 - 0.01**2)
        assert abs(s - expected) < 1e-10

    def test_engagement_limits(self):
        with pytest.raises(ValueError):
            ball_effective_radius(5.0, 6.0)
