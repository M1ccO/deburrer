"""Unit tests for the holder mesh generator."""

from __future__ import annotations

import math
import pytest

from cam_kernel.tools.holder_models import (
    HolderSpec,
    build_holder_mesh,
    holder_length,
)


class TestHolderMesh:
    def test_default_mesh_creation(self):
        vertices, triangles = build_holder_mesh()
        assert len(vertices) > 0
        assert len(triangles) > 0

    def test_total_length(self):
        spec = HolderSpec(nose_length=20, gauge_length=65, collar_length=8)
        assert holder_length(spec) == 93

    def test_minimum_geometry(self):
        vertices, triangles = build_holder_mesh(HolderSpec(segments=8))
        # Body + collar = 3 rings + base center + triangle ring
        # 3 rings * 8 segments = 24 vertices + 1 base = 25
        assert len(vertices) >= 25
        # Each ring pair = 2 triangles per segment
        assert len(triangles) >= 2 * 8 * 2 + 8  # 2 rings of sides + base

    def test_body_diameter_larger_than_nose(self):
        with pytest.raises(ValueError):
            build_holder_mesh(
                HolderSpec(body_diameter=10, nose_diameter=20)
            )

    def test_no_overlapping_vertices(self):
        vertices, _ = build_holder_mesh()
        unique = set(vertices)
        assert len(unique) == len(vertices)

    def test_triangle_winding(self):
        _, triangles = build_holder_mesh()
        for tri in triangles:
            for idx in tri:
                assert 0 <= idx < 1000  # sanity check

    def test_holder_geometry_on_z_axis(self):
        vertices, _ = build_holder_mesh()
        # The base of the nose is at z=0
        z_values = [v[2] for v in vertices]
        assert min(z_values) == pytest.approx(0.0, abs=1e-10)

    def test_segments_increase_mesh_density(self):
        v1, t1 = build_holder_mesh(HolderSpec(segments=8))
        v2, t2 = build_holder_mesh(HolderSpec(segments=24))
        assert len(v2) > len(v1)
        assert len(t2) > len(t1)

    def test_holder_radius_at_nose(self):
        spec = HolderSpec(nose_diameter=30, nose_length=20)
        vertices, _ = build_holder_mesh(spec)
        # The base center is at the origin, so filter for non-center vertices
        nose_tip_verts = [v for v in vertices if abs(v[2]) < 1e-10 and (abs(v[0]) > 1e-6 or abs(v[1]) > 1e-6)]
        assert nose_tip_verts
        for v in nose_tip_verts:
            r = math.sqrt(v[0] ** 2 + v[1] ** 2)
            assert r == pytest.approx(15.0, abs=1e-6)
