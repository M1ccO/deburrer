"""Unit tests for the OCCT payload converter."""

from __future__ import annotations

import pytest

from cam_kernel.geometry.occt_payload import indexed_mesh_to_triangles


class TestIndexedMeshToTriangles:
    def test_single_triangle(self):
        vertices = [0, 0, 0, 1, 0, 0, 0, 1, 0]
        normals = [0, 0, 1, 0, 0, 1, 0, 0, 1]
        indices = [0, 1, 2]
        triangles, tri_normals = indexed_mesh_to_triangles(vertices, normals, indices)
        assert len(triangles) == 1
        assert len(tri_normals) == 1
        assert triangles[0] == ((0, 0, 0), (1, 0, 0), (0, 1, 0))

    def test_multi_triangle_tetrahedron(self):
        vertices = [0, 0, 0, 10, 0, 0, 5, 10, 0, 5, 5, 10]
        normals = [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]
        indices = [0, 1, 2, 0, 1, 3, 0, 2, 3, 1, 2, 3]
        triangles, tri_normals = indexed_mesh_to_triangles(vertices, normals, indices)
        assert len(triangles) == 4
        assert len(tri_normals) == 4

    def test_average_normal(self):
        vertices = [0, 0, 0, 1, 0, 0, 0, 1, 0]
        normals = [0, 0, 1, 0, 0, 1, 0, 0, 1]
        indices = [0, 1, 2]
        triangles, tri_normals = indexed_mesh_to_triangles(vertices, normals, indices)
        assert tri_normals[0] == (0.0, 0.0, 1.0)

    def test_face_normal_when_no_per_vertex_normals(self):
        vertices = [0, 0, 0, 1, 0, 0, 0, 1, 0]
        indices = [0, 1, 2]
        triangles, tri_normals = indexed_mesh_to_triangles(vertices, [], indices)
        assert tri_normals[0] == (0.0, 0.0, 1.0)

    def test_invalid_vertices_length(self):
        with pytest.raises(ValueError):
            indexed_mesh_to_triangles([0, 0, 0, 1, 0], [], [0, 1, 2])

    def test_invalid_indices_length(self):
        with pytest.raises(ValueError):
            indexed_mesh_to_triangles([0, 0, 0, 1, 0, 0, 0, 1, 0], [], [0, 1])

    def test_empty_indices(self):
        triangles, tri_normals = indexed_mesh_to_triangles([], [], [])
        assert len(triangles) == 0
        assert len(tri_normals) == 0
