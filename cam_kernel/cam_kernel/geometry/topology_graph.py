"""B-Rep topology graph via OCP.

Builds and queries a face-edge-vertex adjacency graph from an OCCT shape.
The graph uses stable hash-based IDs so callers don't need to hold OCCT
handles.

Usage::

    from cam_kernel.geometry.topology_graph import build_topology_graph

    graph = build_topology_graph(shape)
    for edge_id in graph.edges_of_face(face_id):
        adjacent = graph.faces_of_edge(edge_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Tuple

Vec3 = Tuple[float, float, float]


class SurfaceType(str, Enum):
    PLANE = "plane"
    CYLINDER = "cylinder"
    CONE = "cone"
    SPHERE = "sphere"
    TORUS = "torus"
    BEZIER = "bezier"
    BSPLINE = "bspline"
    OFFSET = "offset"
    OTHER = "other"


class CurveType(str, Enum):
    LINE = "line"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    BEZIER = "bezier"
    BSPLINE = "bspline"
    OTHER = "other"


_SURFACE_MAP = {
    0: SurfaceType.PLANE,
    1: SurfaceType.CYLINDER,
    2: SurfaceType.CONE,
    3: SurfaceType.SPHERE,
    4: SurfaceType.TORUS,
    5: SurfaceType.BEZIER,
    6: SurfaceType.BSPLINE,
    7: SurfaceType.OFFSET,
}

_CURVE_MAP = {
    0: CurveType.LINE,
    1: CurveType.CIRCLE,
    2: CurveType.ELLIPSE,
    3: CurveType.BEZIER,
    4: CurveType.BSPLINE,
}


@dataclass(frozen=True)
class FaceNode:
    id: str
    area: float
    surface_type: SurfaceType
    is_planar: bool


@dataclass(frozen=True)
class EdgeNode:
    id: str
    length: float
    curve_type: CurveType
    is_linear: bool


@dataclass(frozen=True)
class TopologyGraph:
    faces: Tuple[FaceNode, ...] = ()
    edges: Tuple[EdgeNode, ...] = ()
    face_edge_adjacency: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    edge_face_adjacency: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    def faces_of_edge(self, edge_id: str) -> FrozenSet[str]:
        return self.edge_face_adjacency.get(edge_id, frozenset())

    def edges_of_face(self, face_id: str) -> FrozenSet[str]:
        return self.face_edge_adjacency.get(face_id, frozenset())

    def adjacent_faces(self, face_id: str) -> FrozenSet[str]:
        result = set()
        for edge_id in self.edges_of_face(face_id):
            for other in self.faces_of_edge(edge_id):
                if other != face_id:
                    result.add(other)
        return frozenset(result)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def face_count(self) -> int:
        return len(self.faces)


def build_topology_graph(shape) -> TopologyGraph:
    """Build a topology graph from an OCCT shape.

    Args:
        shape: TopoShape or raw TopoDS_Shape.

    Returns:
        TopologyGraph with face and edge nodes plus adjacency.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt

    raw = shape._shape if hasattr(shape, "_shape") else shape

    # --- Collect faces ---
    face_by_id = {}
    face_data = {}

    fe = TopExp_Explorer(raw, TopAbs_FACE)
    while fe.More():
        face = TopoDS.Face_s(fe.Current())
        fid = _shape_id(face)
        face_by_id[fid] = face

        adapt = BRepAdaptor_Surface(face)
        surf_type = _SURFACE_MAP.get(adapt.GetType(), SurfaceType.OTHER)
        is_planar = adapt.GetType() == GeomAbs_Plane

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()

        face_data[fid] = FaceNode(
            id=fid, area=area, surface_type=surf_type, is_planar=is_planar
        )
        fe.Next()

    # --- Collect edges and build adjacency ---
    edge_by_id = {}
    edge_data = {}
    edge_to_faces = {}
    face_to_edges = {fid: set() for fid in face_by_id}

    ee = TopExp_Explorer(raw, TopAbs_EDGE)
    while ee.More():
        edge = TopoDS.Edge_s(ee.Current())
        eid = _shape_id(edge)
        edge_by_id[eid] = edge
        edge_to_faces[eid] = set()

        adapt = BRepAdaptor_Curve(edge)
        curve_type = _CURVE_MAP.get(adapt.GetType(), CurveType.OTHER)
        length = _curve_length(adapt)

        edge_data[eid] = EdgeNode(
            id=eid, length=length, curve_type=curve_type,
            is_linear=(adapt.GetType() == 0),  # GeomAbs_Line = 0
        )
        ee.Next()

    # --- Edge-to-face adjacency ---
    for fid, face in face_by_id.items():
        exp = TopExp_Explorer(face, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            eid = _shape_id(edge)
            if eid in edge_to_faces:
                edge_to_faces[eid].add(fid)
                face_to_edges[fid].add(eid)
            exp.Next()

    return TopologyGraph(
        faces=tuple(face_data.values()),
        edges=tuple(edge_data.values()),
        face_edge_adjacency={fid: frozenset(es) for fid, es in face_to_edges.items()},
        edge_face_adjacency={eid: frozenset(fs) for eid, fs in edge_to_faces.items()},
    )


def _shape_id(shape) -> str:
    """Stable string ID for an OCCT shape within a session."""
    return str(hash(shape))


def _curve_length(adapt) -> float:
    """Compute the arc length of a curve adaptor."""
    from OCP.gp import gp_Pnt

    start = adapt.FirstParameter()
    end = adapt.LastParameter()
    if abs(end - start) < 1e-12:
        return 0.0

    n_pts = 20
    length = 0.0
    prev = gp_Pnt()
    adapt.D0(start, prev)
    for i in range(1, n_pts + 1):
        t = start + (end - start) * i / n_pts
        curr = gp_Pnt()
        adapt.D0(t, curr)
        length += ((curr.X() - prev.X()) ** 2 + (curr.Y() - prev.Y()) ** 2 + (curr.Z() - prev.Z()) ** 2) ** 0.5
        prev.SetCoord(curr.X(), curr.Y(), curr.Z())
    return length
