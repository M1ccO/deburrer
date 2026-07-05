from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import (
    CandidateFeasibility,
    CandidateGraph,
    CandidateStation,
    ContactIntent,
    FeasibilityState,
    KernelDiagnostic,
    PostureCandidate,
    ToolAssembly,
)


class FeasibilityBackend(Protocol):
    def evaluate(
        self,
        candidate: PostureCandidate,
        intent: ContactIntent,
        tool: ToolAssembly,
    ) -> CandidateFeasibility:
        ...


class NoOpFeasibilityBackend:
    """Explicitly records that collision/clearance was not evaluated."""

    def evaluate(
        self,
        candidate: PostureCandidate,
        intent: ContactIntent,
        tool: ToolAssembly,
    ) -> CandidateFeasibility:
        return CandidateFeasibility(
            FeasibilityState.NOT_CHECKED,
            ("No collision or clearance backend is configured",),
        )


def evaluate_graph(
    graph: CandidateGraph,
    intent: ContactIntent,
    tool: ToolAssembly,
    backend: FeasibilityBackend,
):
    stations = []
    states = set()
    for station in graph.stations:
        candidates = []
        for candidate in station.candidates:
            result = backend.evaluate(candidate, intent, tool)
            states.add(result.state)
            candidates.append(replace(candidate, feasibility=result))
        stations.append(CandidateStation(station.index, tuple(candidates)))

    diagnostics = []
    if FeasibilityState.NOT_CHECKED in states:
        diagnostics.append(
            KernelDiagnostic(
                code="collision.not_checked",
                message=(
                    "Collision and clearance were not checked; the current "
                    "machine output remains provisional"
                ),
                severity="warning",
            )
        )
    return (
        replace(graph, stations=tuple(stations)),
        tuple(diagnostics),
    )
