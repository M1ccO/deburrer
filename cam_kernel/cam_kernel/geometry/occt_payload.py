"""Convert OCCT tessellation data to viewer payload format.

This module bridges the OCCT tessellation output (vertex/face index
arrays) to the triangle+normal format used by the fc_deburr web
preview payload builder.

The output format matches what ``read_binary_stl`` returns:
- triangles: list of (v0, v1, v2) where each v is a 3-tuple
- normals: list of 3-tuples (one per triangle)

These are then combined by ``build_json`` into a flat ``workpiece``
dict with positions and normals.
"""

from __future__ import annotations

from typing import List, Tuple

Vec3 = Tuple[float, float, float]
Triangle = Tuple[Vec3, Vec3, Vec3]


def indexed_mesh_to_triangles(
    vertices: List[float],
    normals: List[float],
    indices: List[int],
) -> Tuple[List[Triangle], List[Vec3]]:
    """Convert an indexed mesh (flat float arrays) to triangle+normal lists.

    Args:
        vertices: Flat list of vertex positions [x0, y0, z0, x1, y1, z1, ...].
        normals: Flat list of per-vertex normals (same length as vertices).
        indices: Flat list of triangle indices [i0, i1, i2, ...] (groups of 3).

    Returns:
        (triangles, normals) where each triangle is a 3-tuple of
        (Vec3, Vec3, Vec3) and each normal is one Vec3 per triangle.
        Vertex normals are averaged per triangle.
    """
    if len(vertices) % 3 != 0:
        raise ValueError("vertices array length must be multiple of 3")
    if len(indices) % 3 != 0:
        raise ValueError("indices array length must be multiple of 3")

    n_verts = len(vertices) // 3
    vert_tuples = [
        (vertices[3 * i], vertices[3 * i + 1], vertices[3 * i + 2])
        for i in range(n_verts)
    ]

    if len(normals) == len(vertices):
        n_normals = [
            (normals[3 * i], normals[3 * i + 1], normals[3 * i + 2])
            for i in range(n_verts)
        ]
    else:
        n_normals = None

    triangles: List[Triangle] = []
    tri_normals: List[Vec3] = []
    for t in range(len(indices) // 3):
        i0, i1, i2 = indices[3 * t], indices[3 * t + 1], indices[3 * t + 2]
        triangles.append((vert_tuples[i0], vert_tuples[i1], vert_tuples[i2]))
        if n_normals is not None:
            tri_normals.append(_average_normal(n_normals[i0], n_normals[i1], n_normals[i2]))
        else:
            tri_normals.append(_face_normal(vert_tuples[i0], vert_tuples[i1], vert_tuples[i2]))

    return triangles, tri_normals


def _average_normal(n0: Vec3, n1: Vec3, n2: Vec3) -> Vec3:
    """Average three normals and re-normalize."""
    nx, ny, nz = n0[0] + n1[0] + n2[0], n0[1] + n1[1] + n2[1], n0[2] + n1[2] + n2[2]
    length = (nx * nx + ny * ny + nz * nz) ** 0.5
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (nx / length, ny / length, nz / length)


def _face_normal(v0: Vec3, v1: Vec3, v2: Vec3) -> Vec3:
    """Compute face normal from three vertices."""
    ux, uy, uz = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    vx, vy, vz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = (nx * nx + ny * ny + nz * nz) ** 0.5
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (nx / length, ny / length, nz / length)
