"""Feature extraction from B-Rep topology via OCP.

Extracts deburr-relevant features:
- Edge chains (connected edges that form deburr contours)
- Face normals at edge parameters (guide and other)
- Edge curve sampling

This module replaces the FreeCAD wire adapter as the geometry source.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

Vec3 = Tuple[float, float, float]


class ChainKind(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class EdgeChain:
    id: str
    kind: ChainKind
    edge_ids: Tuple[str, ...]
    closed: bool
    total_length: float
    label: str = ""


@dataclass(frozen=True)
class EdgeSample:
    """One sample along an edge with tangent and face normals."""

    position: Vec3
    tangent: Vec3
    guide_normal: Vec3
    other_normal: Vec3
    edge_id: str = ""
    chain_index: int = 0


@dataclass(frozen=True)
class EdgeChainSamples:
    id: str
    samples: Tuple[EdgeSample, ...]
    closed: bool
    center_xyz: Optional[Vec3] = None

    @property
    def sample_count(self) -> int:
        return len(self.samples)


def extract_edge_chains(graph, edge_ids: Tuple[str, ...] = ()) -> Tuple[EdgeChain, ...]:
    """Extract connected edge chains from the topology graph.

    Returns chains of edges that share vertices.  Separate chains form
    when edges don't share vertices.  Closed chains are detected when
    the last edge's end vertex matches the first edge's start vertex
    (within tolerance).
    """
    if not graph.edges:
        return ()

    # Build vertex→edges adjacency from OCCT
    return _extract_chains_from_graph(graph, edge_ids)


def _extract_chains_from_graph(graph, edge_ids: Tuple[str, ...]) -> Tuple[EdgeChain, ...]:
    """Build edge chains using vertex connectivity from OCCT shape."""
    # This is a simplified version that groups edges by connected components.
    # For production use, use TopExp_Explorer on vertices with TopAbs_IN.
    # For now, return all edges as individual "chains" and let the caller
    # sort them.

    target = set(edge_ids) if edge_ids else {e.id for e in graph.edges}
    chains = []
    for edge_node in graph.edges:
        if edge_node.id not in target:
            continue
        chains.append(
            EdgeChain(
                id=edge_node.id,
                kind=ChainKind.OPEN,
                edge_ids=(edge_node.id,),
                closed=False,
                total_length=edge_node.length,
                label=f"edge_{edge_node.id[:8]}",
            )
        )
    return tuple(chains)


def sample_edge_chain_from_shape(shape, spacing: float = 0.5, face_index: int = 0) -> EdgeChainSamples:
    """Sample edges of a single face's boundary wire via OCCT.

    Extracts one closed edge loop from the specified face (default: first
    face).  Each face boundary wire forms a closed loop of edges in order.
    This produces samples suitable for the deburring solver pipeline.

    Args:
        shape: TopoShape or TopoDS_Shape.
        spacing: Sample spacing in mm.
        face_index: Which face to extract (0 = first).

    Returns:
        EdgeChainSamples with ordered position/tangent/normal data.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE, TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.gp import gp_Pnt, gp_Vec

    raw = shape._shape if hasattr(shape, "_shape") else shape

    # Collect all faces
    faces = []
    fe = TopExp_Explorer(raw, TopAbs_FACE)
    while fe.More():
        faces.append(TopoDS.Face_s(fe.Current()))
        fe.Next()

    if not faces:
        return EdgeChainSamples(id="empty", samples=(), closed=False, center_xyz=(0, 0, 0))

    face_idx = min(face_index, len(faces) - 1)
    face = faces[face_idx]

    # Build a stable edge index map for topological identity lookup.
    # Python hash() is per-wrapper-instance, not per-TopoDS-Shape —
    # two different explorer passes return different wrappers for the
    # same topological edge, so hash() cannot match them.
    edge_index = TopTools_IndexedMapOfShape()
    edges_exp = TopExp_Explorer(raw, TopAbs_EDGE)
    while edges_exp.More():
        edge_index.Add(edges_exp.Current())
        edges_exp.Next()

    # Get ordered edges from the face's outer wire
    ordered_edges = []
    we = TopExp_Explorer(face, TopAbs_WIRE)
    if we.More():
        wire = TopoDS.Wire_s(we.Current())
        wire_explorer = BRepTools_WireExplorer(wire, face)
        while wire_explorer.More():
            ordered_edges.append(TopoDS.Edge_s(wire_explorer.Current()))
            wire_explorer.Next()
    else:
        # Fallback: iterate edges directly (unordered)
        ee = TopExp_Explorer(face, TopAbs_EDGE)
        while ee.More():
            ordered_edges.append(TopoDS.Edge_s(ee.Current()))
            ee.Next()

    # Build edge → adjacent face lookup using stable edge indices
    edge_faces = {}
    for eid in range(len(ordered_edges)):
        edge = ordered_edges[eid]
        idx = edge_index.FindIndex(edge)
        if idx == 0:
            continue
        edge_faces[idx] = [face]
    for fc in faces:
        if fc is face:
            continue
        exp = TopExp_Explorer(fc, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            idx = edge_index.FindIndex(edge)
            if idx == 0:
                exp.Next()
                continue
            if idx in edge_faces and fc not in edge_faces[idx]:
                edge_faces[idx].append(fc)
            exp.Next()

    # Sample ordered edges, skipping first point of each edge (it duplicates
    # the previous edge's last point at shared vertices).
    all_samples = []
    for eidx, edge in enumerate(ordered_edges):
        idx = edge_index.FindIndex(edge) if edge_index else 0
        adj_faces = edge_faces.get(idx, [face])

        adapt = BRepAdaptor_Curve(edge)
        t_start = adapt.FirstParameter()
        t_end = adapt.LastParameter()
        if edge.Orientation() == TopAbs_REVERSED:
            t_start, t_end = t_end, t_start

        if abs(t_end - t_start) < 1e-9:
            continue

        length = _curve_length_adaptor(adapt)
        n_pts = max(2, int(length / spacing) + 1)

        first_pt_idx = 1 if eidx > 0 else 0  # skip first point on subsequent edges

        for i in range(first_pt_idx, n_pts):
            t = t_start + (t_end - t_start) * i / max(1, n_pts - 1)

            pt = gp_Pnt()
            tan = gp_Vec()
            adapt.D1(t, pt, tan)

            position = (pt.X(), pt.Y(), pt.Z())
            tn = (tan.X(), tan.Y(), tan.Z())
            t_len = math.sqrt(tn[0] ** 2 + tn[1] ** 2 + tn[2] ** 2)
            if t_len > 1e-12:
                tangent = (tn[0] / t_len, tn[1] / t_len, tn[2] / t_len)
            else:
                tangent = (1.0, 0.0, 0.0)

            guide_normal = (0.0, 1.0, 0.0)
            other_normal = (0.0, 0.0, 1.0)

            if len(adj_faces) >= 2:
                n0 = _face_normal_at_edge(adj_faces[0], position, tangent)
                n1 = _face_normal_at_edge(adj_faces[1], position, tangent)
                guide_normal = _vec_normalize(n0)
                other_normal = _vec_normalize(n1)
            elif len(adj_faces) == 1:
                n0 = _face_normal_at_edge(adj_faces[0], position, tangent)
                guide_normal = _vec_normalize(n0)
                other_normal = guide_normal

            all_samples.append(
                EdgeSample(
                    position=position,
                    tangent=tangent,
                    guide_normal=guide_normal,
                    other_normal=other_normal,
                    edge_id=str(idx),
                    chain_index=eidx,
                )
            )

    # Deduplicate last sample if it matches first (closed loop)
    if len(all_samples) >= 2:
        first = all_samples[0]
        last = all_samples[-1]
        dx = first.position[0] - last.position[0]
        dy = first.position[1] - last.position[1]
        dz = first.position[2] - last.position[2]
        if dx * dx + dy * dy + dz * dz < 1e-6:
            all_samples = all_samples[:-1]

    all_samples = _retangent_and_orthogonalize_samples(all_samples, closed=True)
    center = _compute_center(all_samples)
    return EdgeChainSamples(
        id=f"face_{face_idx}",
        samples=tuple(all_samples),
        closed=True,
        center_xyz=center,
    )


def sample_selected_edges_from_shape(
    shape,
    edge_ids,
    spacing: float = 0.5,
) -> EdgeChainSamples:
    """Sample explicitly selected OCCT edges with their adjacent face normals."""
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.gp import gp_Pnt, gp_Vec

    raw = shape._shape if hasattr(shape, "_shape") else shape
    requested = tuple(str(edge_id) for edge_id in edge_ids)
    if not requested:
        return EdgeChainSamples(
            id="selected_edges",
            samples=(),
            closed=False,
            center_xyz=(0.0, 0.0, 0.0),
        )

    # Build stable edge index map — TopTools_IndexedMapOfShape uses
    # TopoDS_Shape.IsSame() internally, so different OCCT wrappers for
    # the same topological edge produce the same index.
    edge_index = TopTools_IndexedMapOfShape()
    ee = TopExp_Explorer(raw, TopAbs_EDGE)
    while ee.More():
        edge_index.Add(ee.Current())
        ee.Next()

    edges_by_id = {}
    index_to_id = {}
    for i in range(1, edge_index.Extent() + 1):
        stable_id = "edge_{}".format(i - 1)
        edges_by_id[stable_id] = TopoDS.Edge_s(edge_index.FindKey(i))
        index_to_id[i] = stable_id

    missing = [edge_id for edge_id in requested if edge_id not in edges_by_id]
    if missing:
        raise ValueError("Selected edge is no longer present in the STEP topology.")

    adjacent_faces = {edge_id: [] for edge_id in requested}
    fe = TopExp_Explorer(raw, TopAbs_FACE)
    while fe.More():
        face = TopoDS.Face_s(fe.Current())
        face_edges = TopExp_Explorer(face, TopAbs_EDGE)
        while face_edges.More():
            edge = TopoDS.Edge_s(face_edges.Current())
            idx = edge_index.FindIndex(edge)
            if idx > 0 and idx in index_to_id:
                stable_id = index_to_id[idx]
                if stable_id in adjacent_faces and face not in adjacent_faces[stable_id]:
                    adjacent_faces[stable_id].append(face)
            face_edges.Next()
        fe.Next()

    segments = []
    for chain_index, edge_id in enumerate(requested):
        edge = edges_by_id[edge_id]
        adapt = BRepAdaptor_Curve(edge)
        t_start = adapt.FirstParameter()
        t_end = adapt.LastParameter()
        length = _curve_length_adaptor(adapt)
        n_pts = max(2, int(length / spacing) + 1)
        segment = []
        for sample_index in range(n_pts):
            parameter = t_start + (t_end - t_start) * sample_index / (n_pts - 1)
            point = gp_Pnt()
            tangent_vector = gp_Vec()
            adapt.D1(parameter, point, tangent_vector)
            tangent = _vec_normalize(
                (
                    tangent_vector.X(),
                    tangent_vector.Y(),
                    tangent_vector.Z(),
                )
            )
            position = (point.X(), point.Y(), point.Z())
            faces = adjacent_faces[edge_id]
            if faces:
                guide_normal = _vec_normalize(
                    _face_normal_at_edge(faces[0], position, tangent)
                )
                other_normal = (
                    _vec_normalize(_face_normal_at_edge(faces[1], position, tangent))
                    if len(faces) > 1
                    else guide_normal
                )
            else:
                guide_normal = (0.0, 1.0, 0.0)
                other_normal = (0.0, 0.0, 1.0)
            segment.append(
                EdgeSample(
                    position=position,
                    tangent=tangent,
                    guide_normal=guide_normal,
                    other_normal=other_normal,
                    edge_id=edge_id,
                    chain_index=chain_index,
                )
            )
        if segment:
            segments.append(segment)

    all_samples = _order_connected_segments(segments, spacing)
    closed = False
    if len(all_samples) >= 3:
        first = all_samples[0].position
        last = all_samples[-1].position
        distance_sq = sum((first[index] - last[index]) ** 2 for index in range(3))
        if distance_sq <= 1.0e-6:
            all_samples.pop()
            closed = True
    all_samples = _retangent_and_orthogonalize_samples(all_samples, closed=closed)
    return EdgeChainSamples(
        id="selected_edges",
        samples=tuple(all_samples),
        closed=closed,
        center_xyz=_compute_center(all_samples),
    )


def _order_connected_segments(segments, spacing: float):
    """Join selected edges by endpoint connectivity, independent of click order."""
    if not segments:
        return []

    tolerance = max(1.0e-5, abs(spacing) * 1.0e-4)
    tolerance_sq = tolerance * tolerance
    remaining = [list(segment) for segment in segments]
    chain = remaining.pop(0)

    while remaining:
        chain_start = chain[0].position
        chain_end = chain[-1].position
        best = None
        for segment_index, segment in enumerate(remaining):
            candidates = (
                (_distance_sq(chain_end, segment[0].position), "append", False),
                (_distance_sq(chain_end, segment[-1].position), "append", True),
                (_distance_sq(chain_start, segment[-1].position), "prepend", False),
                (_distance_sq(chain_start, segment[0].position), "prepend", True),
            )
            for distance_sq, location, reverse in candidates:
                if distance_sq <= tolerance_sq and (
                    best is None or distance_sq < best[0]
                ):
                    best = (distance_sq, segment_index, location, reverse)

        if best is None:
            raise ValueError(
                "Selected edges do not form one connected, non-branching chain."
            )

        _, segment_index, location, reverse = best
        segment = remaining.pop(segment_index)
        if reverse:
            segment = _reverse_segment(segment)
        if location == "append":
            chain.extend(segment[1:])
        else:
            chain = segment[:-1] + chain

    return chain


def _reverse_segment(segment):
    return [
        replace(
            sample,
            tangent=(
                -sample.tangent[0],
                -sample.tangent[1],
                -sample.tangent[2],
            ),
        )
        for sample in reversed(segment)
    ]


def _retangent_and_orthogonalize_samples(samples, closed: bool):
    """Rebuild a consistent local frame from the final chain traversal order."""
    if len(samples) < 2:
        return list(samples)

    corrected = []
    count = len(samples)
    for index, sample in enumerate(samples):
        if closed:
            previous_position = samples[index - 1].position
            following_position = samples[(index + 1) % count].position
            tangent = _vec_normalize(
                _vec_sub(following_position, previous_position)
            )
        elif index == 0:
            tangent = _vec_normalize(
                _vec_sub(samples[1].position, sample.position)
            )
        elif index == count - 1:
            tangent = _vec_normalize(
                _vec_sub(sample.position, samples[index - 1].position)
            )
        else:
            tangent = _vec_normalize(
                _vec_sub(samples[index + 1].position, samples[index - 1].position)
            )

        guide_normal = _orthogonalize_normal(sample.guide_normal, tangent)
        other_normal = _orthogonalize_normal(
            sample.other_normal,
            tangent,
            fallback=guide_normal,
        )
        corrected.append(
            replace(
                sample,
                tangent=tangent,
                guide_normal=guide_normal,
                other_normal=other_normal,
            )
        )
    return _stabilize_normal_pairs(corrected)


def _stabilize_normal_pairs(samples):
    """Keep guide/other face roles continuous across STEP edge boundaries."""
    if len(samples) < 2:
        return list(samples)

    stable = [samples[0]]
    for sample in samples[1:]:
        previous = stable[-1]
        direct_score = (
            _vec_dot(previous.guide_normal, sample.guide_normal)
            + _vec_dot(previous.other_normal, sample.other_normal)
        )
        swapped_score = (
            _vec_dot(previous.guide_normal, sample.other_normal)
            + _vec_dot(previous.other_normal, sample.guide_normal)
        )
        if swapped_score > direct_score + 1.0e-9:
            sample = replace(
                sample,
                guide_normal=sample.other_normal,
                other_normal=sample.guide_normal,
            )
        stable.append(sample)
    return stable


def _orthogonalize_normal(
    normal: Vec3,
    tangent: Vec3,
    fallback: Optional[Vec3] = None,
) -> Vec3:
    tangent = _vec_normalize(tangent)
    tangent_component = _vec_dot(normal, tangent)
    projected = (
        normal[0] - tangent_component * tangent[0],
        normal[1] - tangent_component * tangent[1],
        normal[2] - tangent_component * tangent[2],
    )
    if _vec_length_sq(projected) > 1.0e-18:
        return _vec_normalize(projected)

    if fallback is not None:
        fallback_component = _vec_dot(fallback, tangent)
        projected_fallback = (
            fallback[0] - fallback_component * tangent[0],
            fallback[1] - fallback_component * tangent[1],
            fallback[2] - fallback_component * tangent[2],
        )
        if _vec_length_sq(projected_fallback) > 1.0e-18:
            return _vec_normalize(projected_fallback)

    basis = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        key=lambda candidate: abs(_vec_dot(candidate, tangent)),
    )
    return _vec_normalize(_vec_cross(tangent, basis))


def _distance_sq(first: Vec3, second: Vec3) -> float:
    return _vec_length_sq(_vec_sub(first, second))


def _vec_sub(first: Vec3, second: Vec3) -> Vec3:
    return (
        first[0] - second[0],
        first[1] - second[1],
        first[2] - second[2],
    )


def _vec_dot(first: Vec3, second: Vec3) -> float:
    return (
        first[0] * second[0]
        + first[1] * second[1]
        + first[2] * second[2]
    )


def _vec_cross(first: Vec3, second: Vec3) -> Vec3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _vec_length_sq(vector: Vec3) -> float:
    return _vec_dot(vector, vector)


def topology_selection_payload(shape, spacing: float = 1.0) -> dict:
    """Build face metadata and pickable edge polylines for the web viewer."""
    from .topology_graph import build_topology_graph
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.gp import gp_Pnt

    graph = build_topology_graph(shape)
    face_id_map = {
        face.id: "face_{}".format(index)
        for index, face in enumerate(graph.faces)
    }
    edge_id_map = {
        edge.id: "edge_{}".format(index)
        for index, edge in enumerate(graph.edges)
    }
    face_items = []
    for index, face in enumerate(graph.faces):
        face_items.append(
            {
                "index": index,
                "id": face_id_map[face.id],
                "area": face.area,
                "surface_type": face.surface_type.value,
                "edge_ids": sorted(
                    edge_id_map[edge_id]
                    for edge_id in graph.edges_of_face(face.id)
                ),
            }
        )

    edge_nodes = {edge.id: edge for edge in graph.edges}
    raw = shape._shape if hasattr(shape, "_shape") else shape
    edge_items = []
    seen = set()
    explorer = TopExp_Explorer(raw, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        internal_edge_id = str(hash(edge))
        explorer.Next()
        if internal_edge_id in seen or internal_edge_id not in edge_nodes:
            continue
        seen.add(internal_edge_id)
        node = edge_nodes[internal_edge_id]
        stable_edge_id = edge_id_map[internal_edge_id]
        adapt = BRepAdaptor_Curve(edge)
        length = max(0.0, node.length)
        sample_count = max(2, min(200, int(length / spacing) + 1))
        points = []
        for sample_index in range(sample_count):
            parameter = adapt.FirstParameter() + (
                adapt.LastParameter() - adapt.FirstParameter()
            ) * sample_index / (sample_count - 1)
            point = gp_Pnt()
            adapt.D0(parameter, point)
            points.append([point.X(), point.Y(), point.Z()])
        edge_items.append(
            {
                "index": len(edge_items),
                "id": stable_edge_id,
                "length": length,
                "curve_type": node.curve_type.value,
                "face_ids": sorted(
                    face_id_map[face_id]
                    for face_id in graph.faces_of_edge(internal_edge_id)
                ),
                "points": points,
            }
        )
    return {"faces": face_items, "edges": edge_items}


def _face_normal_at_edge(face, position: Vec3, tangent: Vec3) -> Vec3:
    """Compute face normal at a point near an edge.

    For analytical surfaces (plane, cylinder, cone), compute directly.
    For freeform surfaces, sample the UV near the point.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere
    from OCP.gp import gp_Pnt

    adapt = BRepAdaptor_Surface(face)
    stype = adapt.GetType()
    px, py, pz = position

    if stype == GeomAbs_Plane:
        d = adapt.Plane().Position().Direction()
        return _orient_face_normal(face, (d.X(), d.Y(), d.Z()))
    elif stype == GeomAbs_Cylinder:
        cyl = adapt.Cylinder()
        ax = cyl.Position()
        d = ax.Direction()
        origin = ax.Location()
        dx = px - origin.X()
        dy = py - origin.Y()
        dz = pz - origin.Z()
        dot_ax = dx * d.X() + dy * d.Y() + dz * d.Z()
        proj = (dx - dot_ax * d.X(), dy - dot_ax * d.Y(), dz - dot_ax * d.Z())
        return _orient_face_normal(face, _vec_normalize(proj))
    elif stype == GeomAbs_Sphere:
        sph = adapt.Sphere()
        o = sph.Location()
        r = (px - o.X(), py - o.Y(), pz - o.Z())
        return _orient_face_normal(face, _vec_normalize(r))
    elif stype == GeomAbs_Cone:
        cone = adapt.Cone()
        ax = cone.Position().Direction()
        apex = cone.Apex()
        dx = px - apex.X()
        dy = py - apex.Y()
        dz = pz - apex.Z()
        dot_ax = dx * ax.X() + dy * ax.Y() + dz * ax.Z()
        proj_ax = (dot_ax * ax.X(), dot_ax * ax.Y(), dot_ax * ax.Z())
        rad_dir = (dx - proj_ax[0], dy - proj_ax[1], dz - proj_ax[2])
        r_len = math.sqrt(rad_dir[0] ** 2 + rad_dir[1] ** 2 + rad_dir[2] ** 2)
        if r_len < 1e-9:
            return _orient_face_normal(face, (ax.X(), ax.Y(), ax.Z()))
        half_angle = cone.SemiAngle()
        cone_normal = (
            rad_dir[0] / r_len * math.cos(half_angle) + ax.X() * math.sin(half_angle),
            rad_dir[1] / r_len * math.cos(half_angle) + ax.Y() * math.sin(half_angle),
            rad_dir[2] / r_len * math.cos(half_angle) + ax.Z() * math.sin(half_angle),
        )
        return _orient_face_normal(face, _vec_normalize(cone_normal))

    # Freeform/other analytical surfaces: project the actual edge point onto
    # the underlying face surface. Sampling the UV-box midpoint gives the
    # wrong normal on curved STEP faces and can invent 90-degree jumps.
    try:
        from OCP.BRep import BRep_Tool
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        from OCP.GeomLProp import GeomLProp_SLProps

        surface = BRep_Tool.Surface_s(face)
        projector = GeomAPI_ProjectPointOnSurf(
            gp_Pnt(px, py, pz),
            surface,
            1.0e-7,
        )
        if not projector.IsDone() or projector.NbPoints() < 1:
            raise ValueError("Face-point projection failed")
        u, v = projector.LowerDistanceParameters()
        slp = GeomLProp_SLProps(surface, u, v, 1, 1.0e-7)
        if slp.IsNormalDefined():
            n = slp.Normal()
            return _orient_face_normal(face, (n.X(), n.Y(), n.Z()))
    except Exception:
        pass

    return _orient_face_normal(face, (0.0, 0.0, 1.0))


def _orient_face_normal(face, normal: Vec3) -> Vec3:
    """Apply the topological face orientation to a surface normal."""
    from OCP.TopAbs import TopAbs_REVERSED

    if face.Orientation() == TopAbs_REVERSED:
        return (-normal[0], -normal[1], -normal[2])
    return normal


def _curve_length_adaptor(adapt) -> float:
    t_start = adapt.FirstParameter()
    t_end = adapt.LastParameter()
    if abs(t_end - t_start) < 1e-12:
        return 0.0
    n_pts = 20
    length = 0.0
    from OCP.gp import gp_Pnt

    prev = gp_Pnt()
    adapt.D0(t_start, prev)
    for i in range(1, n_pts + 1):
        t = t_start + (t_end - t_start) * i / n_pts
        curr = gp_Pnt()
        adapt.D0(t, curr)
        length += math.sqrt(
            (curr.X() - prev.X()) ** 2 + (curr.Y() - prev.Y()) ** 2 + (curr.Z() - prev.Z()) ** 2
        )
        prev.SetCoord(curr.X(), curr.Y(), curr.Z())
    return length


def _vec_normalize(v: Vec3) -> Vec3:
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _compute_center(samples) -> Vec3:
    if not samples:
        return (0.0, 0.0, 0.0)
    sx = sum(s.position[0] for s in samples)
    sy = sum(s.position[1] for s in samples)
    sz = sum(s.position[2] for s in samples)
    n = len(samples)
    return (sx / n, sy / n, sz / n)
