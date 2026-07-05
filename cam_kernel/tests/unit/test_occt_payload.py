"""Unit tests for the OCCT payload converter."""

from __future__ import annotations

import pytest

from cam_kernel.geometry.occt_payload import indexed_mesh_to_triangles
from cam_kernel.geometry.occt_session import OcctSession
from cam_kernel.geometry.feature_extract import (
    sample_selected_edges_from_shape,
    topology_selection_payload,
)
from cam_kernel.geometry.tessellation_cache import tessellate_selectable_flat


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


def test_selectable_tessellation_maps_every_triangle_to_a_face():
    shape = OcctSession.make_box(10.0, 20.0, 30.0)
    vertices, normals, indices, triangle_faces = tessellate_selectable_flat(shape)
    assert vertices
    assert normals
    assert indices
    assert len(triangle_faces) == len(indices) // 3
    assert set(triangle_faces) == set(range(shape.face_count))


def test_selected_open_edges_are_ordered_and_have_perpendicular_normals():
    shape = OcctSession.make_box(10.0, 20.0, 30.0)
    topology = topology_selection_payload(shape, spacing=4.0)
    first, second = _find_edge_pair(topology["edges"], connected=True)

    samples = sample_selected_edges_from_shape(
        shape,
        [second["id"], first["id"]],
        spacing=2.0,
    )

    assert not samples.closed
    assert samples.sample_count > 2
    for sample in samples.samples:
        assert _dot(sample.tangent, sample.guide_normal) == pytest.approx(
            0.0, abs=1.0e-9
        )
        assert _dot(sample.tangent, sample.other_normal) == pytest.approx(
            0.0, abs=1.0e-9
        )


def test_disconnected_edge_selection_has_a_specific_error():
    shape = OcctSession.make_box(10.0, 20.0, 30.0)
    topology = topology_selection_payload(shape, spacing=4.0)
    first, second = _find_edge_pair(topology["edges"], connected=False)

    with pytest.raises(ValueError, match="connected, non-branching chain"):
        sample_selected_edges_from_shape(
            shape,
            [first["id"], second["id"]],
            spacing=2.0,
        )


def _find_edge_pair(edges, connected):
    for first_index, first in enumerate(edges):
        first_endpoints = (first["points"][0], first["points"][-1])
        for second in edges[first_index + 1 :]:
            second_endpoints = (second["points"][0], second["points"][-1])
            shares_endpoint = any(
                _distance_sq(left, right) < 1.0e-12
                for left in first_endpoints
                for right in second_endpoints
            )
            if shares_endpoint is connected:
                return first, second
    raise AssertionError("No suitable edge pair found")


def _distance_sq(first, second):
    return sum((first[index] - second[index]) ** 2 for index in range(3))


def _dot(first, second):
    return sum(first[index] * second[index] for index in range(3))
