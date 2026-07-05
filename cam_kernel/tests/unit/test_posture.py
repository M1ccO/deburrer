"""Unit tests for posture cost and optimization."""

from __future__ import annotations

import pytest

from cam_kernel.posture.posture_cost import (
    CostWeights,
    PostureCost,
    deviation_cost,
    soft_limit_cost,
    travel_cost,
    evaluate_posture,
)
from cam_kernel.posture.posture_opt import (
    PostureCandidate,
    select_optimal_sequence,
)


class TestPostureCost:
    def test_deviation_zero(self):
        cost = deviation_cost((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        assert abs(cost) < 1e-10

    def test_deviation_90_deg(self):
        cost = deviation_cost((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        assert abs(cost - 0.9) < 0.001

    def test_travel_cost_zero(self):
        cost = travel_cost((1.0, 0.0, 0.0), None)
        assert cost == 0.0

    def test_soft_limit_inside(self):
        cost = soft_limit_cost(-50.0, -120.0, 120.0)
        assert cost == 0.0

    def test_soft_limit_near_edge(self):
        cost = soft_limit_cost(-118.0, -120.0, 120.0, margin_deg=5.0)
        assert cost > 0.0

    def test_evaluate_posture_default(self):
        cost = evaluate_posture(
            axis=(1.0, 0.0, 0.0),
            preferred_axis=(0.0, 0.0, 1.0),
            b_deg=-50.0,
            c_deg=10.0,
            prev_axis=None,
            prev_b=None,
            prev_c=None,
            b_limits=(-120.0, 120.0),
        )
        assert cost.total > 0.0
        assert cost.soft_limit == 0.0


class TestPostureOptimization:
    def test_select_single_station(self):
        candidates = [
            PostureCandidate(
                station_index=0, axis=(1.0, 0.0, 0.0), b_deg=0.0, c_deg=0.0
            ),
        ]
        result = select_optimal_sequence([candidates])
        assert len(result.candidates) == 1
        assert result.candidates[0].station_index == 0

    def test_select_empty_returns_empty(self):
        result = select_optimal_sequence([])
        assert len(result.candidates) == 0
        assert "Empty" in result.warnings[0]
