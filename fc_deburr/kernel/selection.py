from __future__ import annotations

import math
from typing import Dict, Iterable, Tuple

from ..geometry.vectors import angle_deg
from .models import (
    FeasibilityState,
    MachineCandidate,
    MachineCandidateGraph,
    SelectedSequence,
    SelectionWeights,
)


class NoFeasibleSequenceError(ValueError):
    pass


def select_sequence(
    graph: MachineCandidateGraph,
    weights: SelectionWeights = SelectionWeights(),
) -> SelectedSequence:
    """Select the globally cheapest deterministic sequence.

    Candidate ids form the final tie-break key, so equal-cost graphs produce
    identical results regardless of incidental dictionary ordering.
    """

    stations = tuple(
        tuple(
            candidate
            for candidate in station.candidates
            if candidate.machine_feasible
            and candidate.source.feasibility.state is not FeasibilityState.REJECTED
        )
        for station in graph.stations
    )
    if not stations:
        raise NoFeasibleSequenceError("Candidate graph has no stations")
    for index, candidates in enumerate(stations):
        if not candidates:
            raise NoFeasibleSequenceError(
                "No feasible posture candidates at station %d" % index
            )

    best_result = None
    first_candidates: Iterable[MachineCandidate]
    first_candidates = sorted(stations[0], key=lambda item: item.id)
    for first in first_candidates:
        states: Dict[str, Tuple[float, Tuple[str, ...], Tuple[MachineCandidate, ...]]] = {
            first.id: (
                _node_cost(first, weights),
                (first.id,),
                (first,),
            )
        }
        for candidates in stations[1:]:
            next_states = {}
            for candidate in sorted(candidates, key=lambda item: item.id):
                options = []
                for cost, key, path in states.values():
                    options.append(
                        (
                            cost
                            + _node_cost(candidate, weights)
                            + _transition_cost(path[-1], candidate, weights),
                            key + (candidate.id,),
                            path + (candidate,),
                        )
                    )
                next_states[candidate.id] = min(
                    options, key=lambda item: (item[0], item[1])
                )
            states = next_states

        for cost, key, path in states.values():
            if graph.closed and len(path) > 1:
                cost += _transition_cost(path[-1], path[0], weights)
            result = (cost, key, path)
            if best_result is None or (result[0], result[1]) < (
                best_result[0],
                best_result[1],
            ):
                best_result = result

    if best_result is None:
        raise NoFeasibleSequenceError("No feasible posture sequence")
    return SelectedSequence(best_result[2], best_result[0])


def _node_cost(
    candidate: MachineCandidate, weights: SelectionWeights
) -> float:
    return (
        candidate.source.local_cost
        + candidate.local_cost
        + candidate.source.preferred_deviation_deg * weights.posture_deviation
        + candidate.soft_limit_cost * weights.soft_limit
    )


def _transition_cost(
    previous: MachineCandidate,
    current: MachineCandidate,
    weights: SelectionWeights,
) -> float:
    branch_cost = (
        weights.branch_change
        if previous.branch_id != current.branch_id
        else 0.0
    )
    return (
        angle_deg(previous.source.tool_axis, current.source.tool_axis)
        * weights.tool_axis_transition
        + abs(current.b_deg - previous.b_deg) * weights.b_axis_transition
        + abs(current.c_deg - previous.c_deg) * weights.c_axis_transition
        + current.transition_cost_bias
        + branch_cost
    )
