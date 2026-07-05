from __future__ import annotations

import math
from typing import List, Sequence

from ..domain.errors import SelectionError
from ..domain.models import FeatureLoop, FeatureSample
from ..geometry.vectors import normalize, sub

try:
    import FreeCAD as App
    import Part
except ImportError:  # The core test runner intentionally has no FreeCAD.
    App = None
    Part = None

POINT_TOLERANCE = 1.0e-6


def extract_feature_loop_from_selection(
    selection_ex,
    sample_spacing: float,
    reverse: bool = False,
    feature_id: str = "selected_loop",
) -> FeatureLoop:
    """Convert the active FreeCAD extended selection into domain data.

    Contract: one object, one closed edge chain, one adjoining guide face, and
    one chain vertex identifying C0.
    """

    _require_freecad()
    objects = []
    edges = []
    edge_ids = []
    faces = []
    face_ids = []
    vertices = []
    vertex_ids = []

    for selection in selection_ex:
        if selection.Object is None or not hasattr(selection.Object, "Shape"):
            raise SelectionError("Every selected subelement must belong to a shape")
        objects.append(selection.Object)
        names = tuple(selection.SubElementNames)
        subobjects = tuple(selection.SubObjects)
        if len(names) != len(subobjects):
            raise SelectionError("FreeCAD selection names and objects do not match")
        for name, subobject in zip(names, subobjects):
            if isinstance(subobject, Part.Edge):
                edges.append(subobject)
                edge_ids.append(name)
            elif isinstance(subobject, Part.Face):
                faces.append(subobject)
                face_ids.append(name)
            elif isinstance(subobject, Part.Vertex):
                vertices.append(subobject)
                vertex_ids.append(name)
            else:
                raise SelectionError(
                    "Select edge-chain elements, one guide face, and one C0 vertex"
                )

    unique_objects = {id(item) for item in objects}
    if len(unique_objects) != 1:
        raise SelectionError("All selected geometry must belong to one object")
    if not edges:
        raise SelectionError("Select at least one edge")
    if len(faces) != 1:
        raise SelectionError("Select exactly one guide face")
    if len(vertices) != 1:
        raise SelectionError("Select exactly one C0 vertex")

    source = objects[0]
    return extract_feature_loop_from_shapes(
        parent_shape=source.Shape,
        selected_edges=edges,
        guide_face=faces[0],
        start_vertex=vertices[0],
        sample_spacing=sample_spacing,
        reverse=reverse,
        feature_id=feature_id,
        source_object_id=getattr(source, "Name", ""),
        edge_ids=edge_ids,
        guide_face_id=face_ids[0],
        c0_vertex_id=vertex_ids[0],
    )


def extract_feature_loop_from_shapes(
    parent_shape,
    selected_edges: Sequence,
    guide_face,
    start_vertex,
    sample_spacing: float,
    reverse: bool = False,
    feature_id: str = "feature_loop",
    source_object_id: str = "",
    edge_ids: Sequence[str] = (),
    guide_face_id: str = "",
    c0_vertex_id: str = "",
) -> FeatureLoop:
    _require_freecad()
    if sample_spacing <= 0.0:
        raise SelectionError("Sample spacing must be positive")
    if not selected_edges:
        raise SelectionError("No edges were provided")

    canonical_edges = [
        _canonical_edge(parent_shape, edge) for edge in selected_edges
    ]
    canonical_guide_face = _canonical_face(parent_shape, guide_face)
    if len({edge.hashCode() for edge in canonical_edges}) != len(canonical_edges):
        raise SelectionError("The same edge was selected more than once")

    clusters = Part.sortEdges(canonical_edges)
    if len(clusters) != 1:
        raise SelectionError("Selected edges must form one connected chain")
    ordered = list(clusters[0])
    wire = Part.Wire(ordered)
    if not wire.isClosed():
        raise SelectionError("The first toolpath workflow requires a closed chain")

    start_point = _point(start_vertex.Point)
    ordered = _start_and_orient_edges(ordered, start_point, False)
    source_ids = _edge_id_map(parent_shape, canonical_edges, edge_ids)

    positions = []
    sample_edge_ids = []
    sample_faces = []
    for edge in ordered:
        edge_id = _lookup_edge_id(source_ids, edge)
        adjacent = _adjacent_faces(parent_shape, edge)
        if not adjacent and _edge_lies_on_face(edge, canonical_guide_face):
            # Sketch-derived or independently imported wires can be coincident
            # with a face boundary without sharing OpenCascade topology.
            adjacent = [canonical_guide_face]
        if len(adjacent) not in (1, 2):
            raise SelectionError(
                "%s has %d adjacent faces; expected one free-boundary face "
                "or two solid-edge faces. The selected edge must lie on the "
                "selected guide face"
                % (edge_id or "Edge", len(adjacent))
            )
        guide = next(
            (
                face
                for face in adjacent
                if face.isSame(canonical_guide_face)
            ),
            None,
        )
        if guide is None:
            raise SelectionError(
                "The selected guide face must adjoin every selected edge"
            )
        other = next(
            (
                face
                for face in adjacent
                if not face.isSame(canonical_guide_face)
            ),
            None,
        )

        segments = max(1, int(math.ceil(edge.Length / sample_spacing)))
        for segment in range(segments):
            distance = edge.Length * segment / segments
            parameter = edge.getParameterByLength(distance)
            positions.append(_point(edge.valueAt(parameter)))
            sample_edge_ids.append(edge_id)
            sample_faces.append((guide, other))

    if len(positions) < 3:
        raise SelectionError("Closed feature produced fewer than three samples")
    if _distance(positions[0], start_point) > POINT_TOLERANCE:
        raise SelectionError("Unable to anchor the ordered chain at the C0 vertex")
    if reverse:
        positions = [positions[0]] + list(reversed(positions[1:]))
        sample_edge_ids = [sample_edge_ids[0]] + list(
            reversed(sample_edge_ids[1:])
        )
        sample_faces = [sample_faces[0]] + list(reversed(sample_faces[1:]))

    samples = []
    for index, position in enumerate(positions):
        previous = positions[(index - 1) % len(positions)]
        following = positions[(index + 1) % len(positions)]
        tangent = normalize(sub(following, previous), "sample tangent")
        guide, other = sample_faces[index]
        guide_normal = _face_normal(guide, position)
        other_normal = (
            _face_normal(other, position)
            if other is not None
            else _virtual_boundary_normal(
                guide, position, tangent, guide_normal
            )
        )
        samples.append(
            FeatureSample(
                position=position,
                tangent=tangent,
                guide_normal=guide_normal,
                other_normal=other_normal,
                source_edge_id=sample_edge_ids[index],
            )
        )

    return FeatureLoop(
        id=feature_id,
        samples=tuple(samples),
        closed=True,
        source_object_id=source_object_id,
        source_edge_ids=tuple(label for _, label in source_ids),
        guide_face_id=guide_face_id,
        c0_vertex_id=c0_vertex_id,
        reversed_from_selection=reverse,
    )


def _start_and_orient_edges(edges: List, start_point, reverse: bool):
    candidates = [list(edges), [edge.reversed() for edge in reversed(edges)]]
    selected = None
    for candidate in candidates:
        for index, edge in enumerate(candidate):
            if _distance(_point(edge.firstVertex().Point), start_point) <= POINT_TOLERANCE:
                selected = candidate[index:] + candidate[:index]
                break
        if selected is not None:
            break
    if selected is None:
        raise SelectionError("C0 vertex must be a vertex of the selected chain")
    if reverse:
        selected = [edge.reversed() for edge in reversed(selected)]
        for index, edge in enumerate(selected):
            if _distance(_point(edge.firstVertex().Point), start_point) <= POINT_TOLERANCE:
                selected = selected[index:] + selected[:index]
                break
    return selected


def _edge_id_map(parent_shape, selected_edges, edge_ids):
    result = []
    supplied = tuple(edge_ids)
    for selected_index, edge in enumerate(selected_edges):
        if selected_index < len(supplied):
            label = supplied[selected_index]
        else:
            label = next(
                (
                    "Edge%d" % (index + 1)
                    for index, candidate in enumerate(parent_shape.Edges)
                    if candidate.isSame(edge)
                ),
                "Edge%d" % (selected_index + 1),
            )
        result.append((edge, label))
    return result


def _canonical_edge(parent_shape, selected_edge):
    for candidate in parent_shape.Edges:
        if candidate.isSame(selected_edge):
            return candidate
    matches = [
        candidate
        for candidate in parent_shape.Edges
        if _same_edge_geometry(candidate, selected_edge)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SelectionError(
            "A selected edge could not be mapped back to the source shape"
        )
    raise SelectionError(
        "A selected edge matches multiple source edges; select the source "
        "feature rather than a transformed copy"
    )


def _canonical_face(parent_shape, selected_face):
    for candidate in parent_shape.Faces:
        if candidate.isSame(selected_face):
            return candidate
    matches = [
        candidate
        for candidate in parent_shape.Faces
        if _same_face_geometry(candidate, selected_face)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SelectionError(
            "The selected guide face could not be mapped back to the source shape"
        )
    raise SelectionError(
        "The guide face matches multiple source faces; select the source "
        "feature rather than a transformed copy"
    )


def _adjacent_faces(parent_shape, canonical_edge):
    return [
        face
        for face in parent_shape.Faces
        if any(edge.isSame(canonical_edge) for edge in face.Edges)
    ]


def _edge_lies_on_face(edge, face):
    points = edge.discretize(Number=11)
    tolerance = max(
        POINT_TOLERANCE,
        math.sqrt(
            face.BoundBox.XLength**2
            + face.BoundBox.YLength**2
            + face.BoundBox.ZLength**2
        )
        * 1.0e-7,
    )
    return all(
        face.distToShape(Part.Vertex(point))[0] <= tolerance
        for point in points
    )


def _same_edge_geometry(first, second):
    if abs(first.Length - second.Length) > _scaled_tolerance(
        first.Length, second.Length
    ):
        return False
    if not _same_bounds(first.BoundBox, second.BoundBox):
        return False
    first_points = first.discretize(Number=7)
    second_points = second.discretize(Number=7)
    return _points_lie_on_shape(first_points, second) and _points_lie_on_shape(
        second_points, first
    )


def _same_face_geometry(first, second):
    if abs(first.Area - second.Area) > _scaled_tolerance(
        first.Area, second.Area
    ):
        return False
    if not _same_bounds(first.BoundBox, second.BoundBox):
        return False
    return first.distToShape(second)[0] <= POINT_TOLERANCE


def _points_lie_on_shape(points, shape):
    return all(
        shape.distToShape(Part.Vertex(point))[0] <= POINT_TOLERANCE
        for point in points
    )


def _same_bounds(first, second):
    names = ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")
    return all(
        abs(getattr(first, name) - getattr(second, name))
        <= _scaled_tolerance(getattr(first, name), getattr(second, name))
        for name in names
    )


def _scaled_tolerance(first, second):
    return POINT_TOLERANCE * max(1.0, abs(first), abs(second))


def _lookup_edge_id(source_ids, edge):
    for source_edge, label in source_ids:
        if source_edge.isSame(edge) or _same_edge_geometry(source_edge, edge):
            return label
    return "Edge"


def _virtual_boundary_normal(guide_face, position, tangent, guide_normal):
    """Return the outward in-face normal for a free boundary edge."""

    candidate = normalize(
        _cross(tangent, guide_normal),
        "free-boundary side normal",
    )
    u, v = guide_face.Surface.parameter(App.Vector(*position))
    tangent_u, tangent_v = guide_face.Surface.tangent(u, v)
    du, dv = _vector_to_parameters(candidate, tangent_u, tangent_v)
    step = _boundary_probe_distance(guide_face)
    plus_inside = _is_domain_point(
        guide_face, u + du * step, v + dv * step
    )
    minus_inside = _is_domain_point(
        guide_face, u - du * step, v - dv * step
    )
    if plus_inside != minus_inside:
        return (
            tuple(-component for component in candidate)
            if plus_inside
            else candidate
        )

    # Degenerate UV seams and corner tolerances can make both probes report the
    # same state.  The projected center-of-mass direction is a stable fallback
    # for ordinary trimmed machining faces.
    center_hint = (
        float(guide_face.CenterOfMass.x) - position[0],
        float(guide_face.CenterOfMass.y) - position[1],
        float(guide_face.CenterOfMass.z) - position[2],
    )
    center_hint = tuple(
        center_hint[index]
        - guide_normal[index] * sum(
            center_hint[axis] * guide_normal[axis] for axis in range(3)
        )
        for index in range(3)
    )
    if sum(component * component for component in center_hint) <= 1.0e-16:
        raise SelectionError(
            "Unable to determine the outward side of a free boundary edge"
        )
    if sum(candidate[index] * center_hint[index] for index in range(3)) > 0.0:
        return tuple(-component for component in candidate)
    return candidate


def _vector_to_parameters(vector, tangent_u, tangent_v):
    tu = _point(tangent_u)
    tv = _point(tangent_v)
    a = sum(component * component for component in tu)
    b = sum(tu[index] * tv[index] for index in range(3))
    c = sum(component * component for component in tv)
    x = sum(vector[index] * tu[index] for index in range(3))
    y = sum(vector[index] * tv[index] for index in range(3))
    determinant = a * c - b * b
    if abs(determinant) <= 1.0e-16:
        raise SelectionError("Guide-face parameterization is singular at the edge")
    return (c * x - b * y) / determinant, (a * y - b * x) / determinant


def _is_domain_point(face, u, v):
    surface = face.Surface
    if surface.isUPeriodic():
        period = surface.UPeriod()
        u_min, u_max, _, _ = face.ParameterRange
        while u < u_min:
            u += period
        while u > u_max:
            u -= period
    if surface.isVPeriodic():
        period = surface.VPeriod()
        _, _, v_min, v_max = face.ParameterRange
        while v < v_min:
            v += period
        while v > v_max:
            v -= period
    return bool(face.isPartOfDomain(u, v))


def _boundary_probe_distance(face):
    diagonal = math.sqrt(
        face.BoundBox.XLength**2
        + face.BoundBox.YLength**2
        + face.BoundBox.ZLength**2
    )
    return max(1.0e-5, diagonal * 1.0e-5)


def _cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _face_normal(face, position):
    point = App.Vector(*position)
    u, v = face.Surface.parameter(point)
    return normalize(_point(face.normalAt(u, v)), "face normal")


def _point(vector):
    return float(vector.x), float(vector.y), float(vector.z)


def _distance(a, b):
    delta = sub(a, b)
    return math.sqrt(sum(component * component for component in delta))


def _require_freecad():
    if App is None or Part is None:
        raise RuntimeError("FreeCAD adapter must run inside FreeCAD Python")
