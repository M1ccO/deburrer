from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.models import MachineToolpath, MotionMode, Toolpath
from ..geometry.vectors import normalize
from ..kernel.models import (
    CandidateGraph,
    MachineCandidate,
    MachineCandidateGraph,
    MachineCandidateStation,
)
from .kinematics import (
    bc_from_axis_model,
    model_to_machine,
    solve_ntx_bc,
    workpiece_to_machine,
)
from .profiles import MachineProfile


class MachineKinematicsBackend(Protocol):
    def expand(
        self,
        graph: CandidateGraph,
        profile: MachineProfile,
        motion_mode: MotionMode,
    ) -> MachineCandidateGraph:
        ...

    def solve_path(
        self,
        path: Toolpath,
        profile: MachineProfile,
        motion_mode: MotionMode,
        indexed_b_deg: float | None = None,
        indexed_c_deg: float | None = None,
    ) -> MachineToolpath:
        ...


@dataclass(frozen=True)
class LegacyNtxKinematicsBackend:
    """Candidate adapter around the frozen provisional NTX mapping."""

    b_soft_margin_deg: float = 15.0

    def expand(
        self,
        graph: CandidateGraph,
        profile: MachineProfile,
        motion_mode: MotionMode,
    ) -> MachineCandidateGraph:
        previous_c = None
        stations = []
        for station in graph.stations:
            machine_candidates = []
            for candidate in station.candidates:
                xyz_work = workpiece_to_machine(
                    candidate.xyz, profile.workpiece
                )
                xyz = model_to_machine(xyz_work, profile)
                b_deg, c_deg = bc_from_axis_model(
                    candidate.tool_axis, profile, previous_c
                )
                previous_c = c_deg
                b_margin = min(
                    b_deg - profile.b_min_deg,
                    profile.b_max_deg - b_deg,
                )
                c_margin = _c_margin(c_deg, profile)
                reasons = []
                if b_margin < 0.0:
                    reasons.append("B axis is outside configured limits")
                if c_margin is not None and c_margin < 0.0:
                    reasons.append("C axis is outside configured limits")
                soft_cost = max(
                    0.0, self.b_soft_margin_deg - b_margin
                ) ** 2
                machine_candidates.append(
                    MachineCandidate(
                        id=candidate.id + ":legacy",
                        source=candidate,
                        xyz_radius=xyz,
                        b_deg=b_deg,
                        c_deg=c_deg,
                        branch_id="legacy",
                        b_limit_margin_deg=b_margin,
                        c_limit_margin_deg=c_margin,
                        machine_feasible=not reasons,
                        rejection_reasons=tuple(reasons),
                        soft_limit_cost=soft_cost,
                    )
                )
            stations.append(
                MachineCandidateStation(
                    station.index, tuple(machine_candidates)
                )
            )
        return MachineCandidateGraph(
            feature_id=graph.feature_id,
            operation_id=graph.operation_id,
            tool_id=graph.tool_id,
            stations=tuple(stations),
            closed=graph.closed,
        )

    def solve_path(
        self,
        path: Toolpath,
        profile: MachineProfile,
        motion_mode: MotionMode,
        indexed_b_deg: float | None = None,
        indexed_c_deg: float | None = None,
    ) -> MachineToolpath:
        return solve_ntx_bc(
            path,
            profile,
            motion_mode=motion_mode,
            indexed_b_deg=indexed_b_deg,
            indexed_c_deg=indexed_c_deg,
        )


def _c_margin(c_deg: float, profile: MachineProfile):
    margins = []
    if profile.c_min_deg is not None:
        margins.append(c_deg - profile.c_min_deg)
    if profile.c_max_deg is not None:
        margins.append(profile.c_max_deg - c_deg)
    return min(margins) if margins else None
