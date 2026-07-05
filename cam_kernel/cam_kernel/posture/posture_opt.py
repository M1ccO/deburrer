"""Posture optimization — global sequence selection.

Given a set of posture candidates at each contact station, selects the
globally optimal sequence using dynamic programming (Viterbi-style).

Algorithm:

1. Build a lattice of (station × candidate) nodes.
2. Compute per-node costs (deviation, joint-space limits).
3. Compute per-edge costs (travel, branch changes).
4. Find the minimum-cost path through the lattice.

The output is a deterministic, continuous sequence — no random search
and no branch flips, provided the topology allows it.

Bridges to ``fc_deburr.kernel.selection`` which implements the same
algorithm on the existing domain types.

TODO:
 - Multi-branch expansion for redundant kinematics
 - Hysteresis to prevent oscillation at branch boundaries
 - Parallel optimization for large toolpaths
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .posture_cost import (
    CostWeights,
    PostureCost,
    evaluate_posture,
)

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class PostureCandidate:
    station_index: int
    axis: Vec3
    b_deg: float
    c_deg: float
    cost: PostureCost = PostureCost()

    @property
    def id(self) -> str:
        return f"s{self.station_index}_b{self.b_deg:.1f}_c{self.c_deg:.1f}"


@dataclass
class PosturePath:
    candidates: Tuple[PostureCandidate, ...]
    total_cost: float
    warnings: Tuple[str, ...] = ()


def select_optimal_sequence(
    stations: List[List[PostureCandidate]],
    weights: CostWeights = CostWeights(),
    b_limits: tuple = (-120.0, 120.0),
) -> PosturePath:
    """Select the minimum-cost sequence using dynamic programming.

    TODO: Full DP implementation with path reconstruction.
    """
    if not stations or not stations[0]:
        return PosturePath(candidates=(), total_cost=0.0, warnings=("Empty input",))

    selected = [stations[i][0] for i in range(len(stations))]
    total = sum(
        evaluate_posture(
            c.axis,
            c.axis,
            c.b_deg,
            c.c_deg,
            selected[i - 1].axis if i > 0 else None,
            selected[i - 1].b_deg if i > 0 else None,
            selected[i - 1].c_deg if i > 0 else None,
            b_limits,
            weights,
        ).total
        for i, c in enumerate(selected)
    )
    return PosturePath(candidates=tuple(selected), total_cost=total)


def expand_machine_candidates(
    contact_points,
    kinematics,
    preferred_axis_fn=None,
    branches=None,
) -> List[List[PostureCandidate]]:
    """Expand contact points into machine-space posture candidates.

    For each contact point, computes all kinematically valid (B, C)
    pairs from the tool axis and wraps them as ``PostureCandidate``
    values.

    TODO: Multi-branch expansion.
    """
    raise NotImplementedError("Candidate expansion not yet implemented")
