"""Tessellation cache via OCP.

Generates and caches triangle meshes from B-Rep shapes using OCCT's
incremental mesher.  Used by the viewer (Three.js) and collision
engine (FCL).

Usage::

    from cam_kernel.geometry.tessellation_cache import tessellate

    vertices, triangles, normals = tessellate(shape, tolerance=0.1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass
class TriMesh:
    vertices: Tuple[Vec3, ...] = ()
    triangles: Tuple[Tuple[int, int, int], ...] = ()
    normals: Tuple[Vec3, ...] = ()


@dataclass
class TessellationCache:
    """Caches tessellated meshes keyed by shape ID and tolerance."""

    tolerance_mm: float = 0.1
    _cache: Dict[str, TriMesh] = field(default_factory=dict)

    def get_or_compute(self, shape, shape_id: str = "", tolerance_mm: Optional[float] = None) -> TriMesh:
        tol = tolerance_mm or self.tolerance_mm
        sid = shape_id or str(hash(shape._shape if hasattr(shape, "_shape") else shape))
        cache_key = f"{sid}_{tol}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        mesh = tessellate(shape, tol)
        self._cache[cache_key] = mesh
        return mesh

    def clear(self) -> None:
        self._cache.clear()


def tessellate(shape, tolerance_mm: float = 0.1) -> TriMesh:
    """Tessellate a shape to triangles via OCCT.

    Args:
        shape: TopoShape or raw TopoDS_Shape.
        tolerance_mm: Linear deflection tolerance (mm).

    Returns:
        TriMesh with vertices, triangle indices, and per-vertex normals.
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.Poly import Poly_Triangulation
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.gp import gp_Pnt

    raw = shape._shape if hasattr(shape, "_shape") else shape

    mesh = BRepMesh_IncrementalMesh(raw, tolerance_mm, False, 0.5)
    mesh.Perform()

    vertices = []
    normals = []
    triangles = []
    vertex_map = {}
    v_offset = 0

    fe = TopExp_Explorer(raw, TopAbs_FACE)
    while fe.More():
        face = TopoDS.Face_s(fe.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)

        if triangulation is None or triangulation.NbTriangles() == 0:
            fe.Next()
            continue

        n_nodes = triangulation.NbNodes()
        n_tris = triangulation.NbTriangles()

        transform = loc.Transformation()
        local_verts = []
        for i in range(1, n_nodes + 1):
            p = triangulation.Node(i)
            tp = p.Transformed(transform)
            local_verts.append((tp.X(), tp.Y(), tp.Z()))

        # Build vertex map for deduplication
        remap = {}
        for i, (x, y, z) in enumerate(local_verts):
            key = (round(x, 6), round(y, 6), round(z, 6))
            if key not in vertex_map:
                vertex_map[key] = len(vertices)
                vertices.append((x, y, z))
            remap[i] = vertex_map[key]

        # Read triangles
        for ti in range(1, n_tris + 1):
            t = triangulation.Triangle(ti)
            a = remap[t.Value(1) - 1]
            b = remap[t.Value(2) - 1]
            c = remap[t.Value(3) - 1]
            triangles.append((a, b, c))

        # Add normals placeholder (will be computed)
        for _ in local_verts:
            normals.append((0.0, 0.0, 1.0))

        fe.Next()

    # Compute per-face normals
    normals = _compute_normals(vertices, triangles)

    return TriMesh(
        vertices=tuple(vertices),
        triangles=tuple(triangles),
        normals=tuple(normals),
    )


def tessellate_flat(shape, tolerance_mm: float = 0.1):
    """Tessellate and return flat arrays for Three.js / FCL.

    Returns:
        (vertices_flat, face_normals_flat, indices) as flat lists of floats.
    """
    mesh = tessellate(shape, tolerance_mm)
    vflat = []
    for v in mesh.vertices:
        vflat.extend(v)
    iflat = []
    for t in mesh.triangles:
        iflat.extend(t)
    nflat = []
    for n in mesh.normals:
        nflat.extend(n)
    return vflat, nflat, iflat


def _compute_normals(vertices, triangles):
    """Compute per-face normals (flat shading)."""
    normals = [(0.0, 0.0, 1.0)] * len(vertices)
    from math import sqrt

    for t in triangles:
        a = vertices[t[0]]
        b = vertices[t[1]]
        c = vertices[t[2]]
        ux = b[0] - a[0]; uy = b[1] - a[1]; uz = b[2] - a[2]
        vx = c[0] - a[0]; vy = c[1] - a[1]; vz = c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        length = sqrt(nx * nx + ny * ny + nz * nz)
        if length > 1e-12:
            nx /= length; ny /= length; nz /= length
        for idx in t:
            normals[idx] = (nx, ny, nz)
    return normals
