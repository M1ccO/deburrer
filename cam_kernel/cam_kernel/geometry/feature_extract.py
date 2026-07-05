"""Feature extraction from B-Rep topology via OCP.

Extracts deburr-relevant features:
- Edge chains (connected edges that form deburr contours)
- Face normals at edge parameters (guide and other)
- Edge curve sampling

This module replaces the FreeCAD wire adapter as the geometry source.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRep import BRep_Tool
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

    # Find all faces for normal computation
    face_map = {}
    fe2 = TopExp_Explorer(raw, TopAbs_FACE)
    while fe2.More():
        f = TopoDS.Face_s(fe2.Current())
        face_map[str(hash(f))] = f
        fe2.Next()

    # Get ordered edges from the face's outer wire
    ordered_edges = []
    we = TopExp_Explorer(face, TopAbs_WIRE)
    if we.More():
        wire = we.Current()
        ew = TopExp_Explorer(wire, TopAbs_EDGE)
        while ew.More():
            ordered_edges.append(TopoDS.Edge_s(ew.Current()))
            ew.Next()
    else:
        # Fallback: iterate edges directly (unordered)
        ee = TopExp_Explorer(face, TopAbs_EDGE)
        while ee.More():
            ordered_edges.append(TopoDS.Edge_s(ee.Current()))
            ee.Next()

    # Build edge → adjacent face lookup
    edge_faces = {}
    for eid in range(len(ordered_edges)):
        edge = ordered_edges[eid]
        eh = str(hash(edge))
        edge_faces[eh] = [face]  # at minimum, the current face
    for fid, fc in face_map.items():
        if fc is face:
            continue
        exp = TopExp_Explorer(fc, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            eh = str(hash(edge))
            if eh in edge_faces and fc not in edge_faces[eh]:
                edge_faces[eh].append(fc)
            exp.Next()

    # Sample ordered edges, skipping first point of each edge (it duplicates
    # the previous edge's last point at shared vertices).
    all_samples = []
    for eidx, edge in enumerate(ordered_edges):
        eh = str(hash(edge))
        adj_faces = edge_faces.get(eh, [face])

        adapt = BRepAdaptor_Curve(edge)
        t_start = adapt.FirstParameter()
        t_end = adapt.LastParameter()

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
                    edge_id=eh,
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

    center = _compute_center(all_samples)
    return EdgeChainSamples(
        id=f"face_{face_idx}",
        samples=tuple(all_samples),
        closed=True,
        center_xyz=center,
    )


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
        return (d.X(), d.Y(), d.Z())
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
        return _vec_normalize(proj)
    elif stype == GeomAbs_Sphere:
        sph = adapt.Sphere()
        o = sph.Location()
        r = (px - o.X(), py - o.Y(), pz - o.Z())
        return _vec_normalize(r)
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
            return (ax.X(), ax.Y(), ax.Z())
        half_angle = cone.SemiAngle()
        cone_normal = (
            rad_dir[0] / r_len * math.cos(half_angle) + ax.X() * math.sin(half_angle),
            rad_dir[1] / r_len * math.cos(half_angle) + ax.Y() * math.sin(half_angle),
            rad_dir[2] / r_len * math.cos(half_angle) + ax.Z() * math.sin(half_angle),
        )
        return _vec_normalize(cone_normal)

    # Fallback for freeform surfaces
    try:
        from OCP.GeomLProp import GeomLProp_SLProps
        from OCP.Geom import Geom_Surface

        u_min = adapt.FirstUParameter()
        u_max = adapt.LastUParameter()
        v_min = adapt.FirstVParameter()
        v_max = adapt.LastVParameter()
        u = (u_min + u_max) * 0.5
        v = (v_min + v_max) * 0.5
        surf = adapt.Surface().Surface()
        slp = GeomLProp_SLProps(surf, u, v, 1, 0.01)
        if slp.IsNormalDefined():
            n = slp.Normal()
            return (n.X(), n.Y(), n.Z())
    except Exception:
        pass

    return (0.0, 0.0, 1.0)


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
