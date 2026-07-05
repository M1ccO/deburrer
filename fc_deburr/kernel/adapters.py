from __future__ import annotations

from dataclasses import replace

from ..domain.models import (
    Operation,
    PathPoint,
    ToolDefinition,
    ToolKind,
    Toolpath,
)
from .models import (
    CandidateGraph,
    CandidateStation,
    ContactIntent,
    EngagementLocation,
    PostureCandidate,
    SelectedSequence,
    ToolAssembly,
)


def contact_intent_from_operation(
    feature_id: str,
    tool: ToolDefinition,
    operation: Operation,
) -> ContactIntent:
    if tool.kind is ToolKind.CHAMFER:
        target_mode = "constant_width"
        target_amount = operation.target_width
        engagement = EngagementLocation(
            "contact_radius", tool.contact_radius
        )
    else:
        target_mode = "rounded_break"
        target_amount = operation.ball_engagement
        engagement = EngagementLocation(
            "radial_infeed", operation.ball_engagement
        )
    return ContactIntent(
        feature_id=feature_id,
        operation_id=operation.id,
        tool_id=tool.id,
        target_mode=target_mode,
        target_amount_mm=target_amount,
        preferred_engagement=engagement,
    )


def tool_assembly_from_definition(tool: ToolDefinition) -> ToolAssembly:
    return ToolAssembly(cutter=tool)


def toolpath_to_candidate_graph(
    path: Toolpath,
    intent: ContactIntent,
) -> CandidateGraph:
    """Adapt today's authoritative analytic path to one candidate per station."""

    stations = tuple(
        CandidateStation(
            index=index,
            candidates=(
                PostureCandidate(
                    id="%06d:analytic" % index,
                    station_index=index,
                    seq=point.seq,
                    xyz=point.xyz,
                    tool_axis=point.tool_axis,
                    motion=point.motion,
                    contact_xyz=point.contact_xyz,
                    target_a_xyz=point.target_a_xyz,
                    target_b_xyz=point.target_b_xyz,
                    tangent=point.tangent,
                    feed=point.feed,
                    flags=point.flags,
                    engagement=intent.preferred_engagement,
                ),
            ),
        )
        for index, point in enumerate(path.points)
    )
    # Analytic solvers currently include an explicit duplicate closure point.
    # Do not add a second implicit closing transition in the selector.
    return CandidateGraph(
        feature_id=path.feature_id,
        operation_id=path.operation_id,
        tool_id=path.tool_id,
        stations=stations,
        closed=False,
    )


def selected_sequence_to_toolpath(
    selected: SelectedSequence,
    template: Toolpath,
) -> Toolpath:
    points = tuple(
        PathPoint(
            seq=index,
            xyz=item.source.xyz,
            tool_axis=item.source.tool_axis,
            motion=item.source.motion,
            contact_xyz=item.source.contact_xyz,
            target_a_xyz=item.source.target_a_xyz,
            target_b_xyz=item.source.target_b_xyz,
            tangent=item.source.tangent,
            feed=item.source.feed,
            flags=item.source.flags,
        )
        for index, item in enumerate(selected.candidates)
    )
    return replace(template, points=points)
