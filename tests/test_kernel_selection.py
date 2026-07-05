import pytest

from fc_deburr.domain.models import MotionKind
from fc_deburr.kernel.models import (
    CandidateFeasibility,
    FeasibilityState,
    MachineCandidate,
    MachineCandidateGraph,
    MachineCandidateStation,
    PostureCandidate,
    SelectionWeights,
)
from fc_deburr.kernel.selection import (
    NoFeasibleSequenceError,
    select_sequence,
)


def _part(candidate_id, station, local_cost=0.0, state=FeasibilityState.ACCEPTED):
    return PostureCandidate(
        id=candidate_id,
        station_index=station,
        seq=station,
        xyz=(float(station), 0.0, 0.0),
        tool_axis=(0.0, 0.0, 1.0),
        motion=MotionKind.CUT,
        local_cost=local_cost,
        feasibility=CandidateFeasibility(state),
    )


def _machine(
    candidate_id,
    station,
    b_deg,
    *,
    local_cost=0.0,
    soft_cost=0.0,
    branch="main",
    feasible=True,
    state=FeasibilityState.ACCEPTED,
):
    source = _part(candidate_id, station, local_cost, state)
    return MachineCandidate(
        id=candidate_id + ":" + branch,
        source=source,
        xyz_radius=source.xyz,
        b_deg=b_deg,
        c_deg=0.0,
        branch_id=branch,
        b_limit_margin_deg=30.0,
        machine_feasible=feasible,
        soft_limit_cost=soft_cost,
    )


def _graph(*stations, closed=False):
    return MachineCandidateGraph(
        feature_id="feature",
        operation_id="operation",
        tool_id="tool",
        stations=tuple(
            MachineCandidateStation(index, tuple(candidates))
            for index, candidates in enumerate(stations)
        ),
        closed=closed,
    )


def test_selector_uses_global_transition_cost_not_local_greedy_choice():
    graph = _graph(
        [_machine("start", 0, 0.0)],
        [
            _machine("jump", 1, 100.0),
            _machine("smooth", 1, 1.0, local_cost=5.0),
        ],
        [_machine("end", 2, 2.0)],
    )
    weights = SelectionWeights(
        posture_deviation=0.0,
        tool_axis_transition=0.0,
        b_axis_transition=1.0,
        c_axis_transition=0.0,
        soft_limit=0.0,
        branch_change=0.0,
    )

    result = select_sequence(graph, weights)

    assert [item.source.id for item in result.candidates] == [
        "start",
        "smooth",
        "end",
    ]


def test_selector_tie_breaks_by_stable_candidate_id():
    graph = _graph(
        [
            _machine("z-choice", 0, 0.0),
            _machine("a-choice", 0, 0.0),
        ]
    )

    result = select_sequence(graph, SelectionWeights())

    assert result.candidates[0].source.id == "a-choice"


def test_rejected_and_machine_infeasible_candidates_are_removed():
    graph = _graph(
        [
            _machine(
                "part-rejected",
                0,
                0.0,
                state=FeasibilityState.REJECTED,
            ),
            _machine("machine-rejected", 0, 0.0, feasible=False),
            _machine("accepted", 0, 0.0, local_cost=10.0),
        ]
    )

    result = select_sequence(graph)

    assert result.candidates[0].source.id == "accepted"


def test_no_feasible_station_has_structured_failure():
    graph = _graph([_machine("blocked", 0, 0.0, feasible=False)])

    with pytest.raises(NoFeasibleSequenceError, match="station 0"):
        select_sequence(graph)


def test_closed_graph_includes_last_to_first_transition():
    graph = _graph(
        [_machine("first", 0, 0.0)],
        [_machine("last", 1, 10.0)],
        closed=True,
    )
    weights = SelectionWeights(
        posture_deviation=0.0,
        tool_axis_transition=0.0,
        b_axis_transition=1.0,
        c_axis_transition=0.0,
        soft_limit=0.0,
        branch_change=0.0,
    )

    result = select_sequence(graph, weights)

    assert result.total_cost == 20.0


def test_soft_limit_and_branch_change_costs_affect_selection():
    graph = _graph(
        [_machine("start", 0, 0.0, branch="main")],
        [
            _machine(
                "near-limit", 1, 0.0, branch="main", soft_cost=25.0
            ),
            _machine(
                "branch-hop", 1, 0.0, branch="alternate", local_cost=1.0
            ),
            _machine(
                "safe", 1, 0.0, branch="main", local_cost=5.0
            ),
        ],
    )
    weights = SelectionWeights(
        posture_deviation=0.0,
        tool_axis_transition=0.0,
        b_axis_transition=0.0,
        c_axis_transition=0.0,
        soft_limit=1.0,
        branch_change=100.0,
    )

    result = select_sequence(graph, weights)

    assert result.candidates[1].source.id == "safe"
