from __future__ import annotations

import math

from ..domain.errors import SelectionError
from ..domain.models import FeatureLoop, FeatureSample
from ..geometry.vectors import cross, dot, normalize, scale, sub

try:
    import Part
except ImportError:
    Part = None


def extract_wire_loop_from_selection(
    selection_ex,
    sample_spacing: float,
    reverse: bool = False,
    feature_id: str = "selected_wire",
) -> FeatureLoop:
    """Extract an open or closed wire without requiring faces or a clicked vertex."""

    if Part is None:
        raise RuntimeError("Wire extraction must run inside FreeCAD Python")
    if sample_spacing <= 0.0:
        raise SelectionError("Sample spacing must be positive")

    edges = []
    edge_ids = []
    source_names = []
    for selection in selection_ex:
        if selection.Object is not None:
            source_names.append(getattr(selection.Object, "Name", ""))
        for name, subobject in zip(
            selection.SubElementNames, selection.SubObjects
        ):
            if not isinstance(subobject, Part.Edge):
                raise SelectionError(
                    "Wire Deburr needs only edge selections"
                )
            edges.append(subobject)
            edge_ids.append(str(name))
    if not edges:
        raise SelectionError("Select a wire or its connected edges")

    clusters = Part.sortEdges(edges)
    if len(clusters) != 1:
        raise SelectionError("Selected edges must form one connected wire")
    wire = Part.Wire(clusters[0])
    wire_closed = wire.isClosed()

    points = [_point(point) for point in wire.discretize(Distance=sample_spacing)]
    if len(points) >= 2 and _distance(points[0], points[-1]) <= 1.0e-7:
        points.pop()
    min_required = 3 if wire_closed else 2
    if len(points) < min_required:
        raise SelectionError(
            "The selected %s produced fewer than %d samples"
            % ("closed wire" if wire_closed else "open wire", min_required)
        )

    center = tuple(
        (min(point[axis] for point in points) + max(point[axis] for point in points))
        * 0.5
        for axis in range(3)
    )

    if wire_closed:
        start_index = max(
            range(len(points)),
            key=lambda index: (
                points[index][1] - center[1],
                points[index][2] - center[2],
            ),
        )
        points = points[start_index:] + points[:start_index]
    if reverse:
        points = [points[0]] + list(reversed(points[1:]))

    samples = []
    for index, position in enumerate(points):
        if wire_closed:
            previous = points[(index - 1) % len(points)]
            following = points[(index + 1) % len(points)]
        elif index == 0:
            previous = points[0]
            following = points[1]
        elif index == len(points) - 1:
            previous = points[index - 1]
            following = points[index]
        else:
            previous = points[index - 1]
            following = points[index + 1]
        tangent = normalize(sub(following, previous), "wire tangent")
        if wire_closed:
            radial = (0.0, position[1] - center[1], position[2] - center[2])
            radial = sub(radial, scale(tangent, dot(radial, tangent)))
            if dot(radial, radial) <= 1.0e-14:
                radial = cross((1.0, 0.0, 0.0), tangent)
            guide = normalize(radial, "wire radial posture")
        else:
            ref = (0.0, 1.0, 0.0)
            if abs(dot(tangent, ref)) > 0.99:
                ref = (0.0, 0.0, 1.0)
            guide = normalize(cross(tangent, ref), "wire guide")
        other = normalize(cross(tangent, guide), "wire side posture")
        samples.append(
            FeatureSample(
                position=position,
                tangent=tangent,
                guide_normal=guide,
                other_normal=other,
                source_edge_id=edge_ids[0] if len(edge_ids) == 1 else "Wire",
            )
        )

    return FeatureLoop(
        id=feature_id,
        samples=tuple(samples),
        closed=wire_closed,
        center_xyz=center,
        source_object_id=",".join(name for name in source_names if name),
        source_edge_ids=tuple(edge_ids),
        c0_vertex_id="CENTER_MAX_Y" if wire_closed else "",
        reversed_from_selection=reverse,
    )


def _point(vector):
    return float(vector.x), float(vector.y), float(vector.z)


def _distance(first, second):
    return math.sqrt(
        sum((first[index] - second[index]) ** 2 for index in range(3))
    )
