import math

import pytest

from fc_deburr.domain.models import MotionKind, MotionMode
from fc_deburr.kernel.models import (
    CandidateGraph,
    CandidateStation,
    PostureCandidate,
)
from fc_deburr.machine.backends import LegacyNtxKinematicsBackend
from fc_deburr.machine.kinematics import axis_model_from_bc
from fc_deburr.machine.profiles import MachineProfile


def _graph(tool_axis):
    candidate = PostureCandidate(
        id="candidate",
        station_index=0,
        seq=0,
        xyz=(1.0, 2.0, 3.0),
        tool_axis=tool_axis,
        motion=MotionKind.CUT,
    )
    return CandidateGraph(
        feature_id="feature",
        operation_id="operation",
        tool_id="tool",
        stations=(CandidateStation(0, (candidate,)),),
    )


def test_legacy_backend_records_hard_b_limit_failure_and_margin():
    profile = MachineProfile(b_max_deg=30.0)
    graph = _graph(axis_model_from_bc(60.0, 0.0, profile))

    expanded = LegacyNtxKinematicsBackend().expand(
        graph, profile, MotionMode.SIMULTANEOUS_5_AXIS
    )
    candidate = expanded.stations[0].candidates[0]

    assert candidate.b_deg == pytest.approx(60.0)
    assert candidate.b_limit_margin_deg == pytest.approx(-30.0)
    assert not candidate.machine_feasible
    assert candidate.rejection_reasons


def test_legacy_backend_records_rising_soft_limit_cost():
    profile = MachineProfile(b_max_deg=60.0)
    graph = _graph(axis_model_from_bc(55.0, 0.0, profile))

    expanded = LegacyNtxKinematicsBackend(
        b_soft_margin_deg=15.0
    ).expand(graph, profile, MotionMode.SIMULTANEOUS_5_AXIS)
    candidate = expanded.stations[0].candidates[0]

    assert candidate.machine_feasible
    assert candidate.b_limit_margin_deg == pytest.approx(5.0)
    assert candidate.soft_limit_cost == pytest.approx(100.0)


def test_fixed_c_candidate_matches_frozen_start_at_zero_behavior():
    graph = _graph((1.0, 0.0, 0.0))
    profile = MachineProfile(c_zero_offset_deg=37.0)

    expanded = LegacyNtxKinematicsBackend().expand(
        graph, profile, MotionMode.SIMULTANEOUS_5_AXIS
    )

    assert expanded.stations[0].candidates[0].c_deg == 37.0
