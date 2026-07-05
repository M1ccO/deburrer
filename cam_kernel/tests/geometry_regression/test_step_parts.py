"""Regression tests for STEP file loading and feature extraction.

Each test loads a known STEP file from ``tests/geometry_regression/parts/``
and validates that the OCCT pipeline produces the expected counts.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

# Allow tests to import from the cam_kernel package
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from cam_kernel.cam_kernel.geometry.occt_session import OcctSession
from cam_kernel.cam_kernel.geometry.topology_graph import build_topology_graph
from cam_kernel.cam_kernel.geometry.tessellation_cache import tessellate
from cam_kernel.cam_kernel.geometry.feature_extract import sample_edge_chain_from_shape


PARTS_DIR = Path(__file__).resolve().parent / "parts"


def _load_part(name: str):
    """Load a part from PARTS_DIR/<name>.step."""
    path = PARTS_DIR / f"{name}.step"
    if not path.exists():
        pytest.skip(f"Part file not found: {path}")
    meta_path = PARTS_DIR / f"{name}.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    with OcctSession() as sess:
        shape = sess.load_step(str(path))
    return shape, meta


def test_box_loads():
    shape, meta = _load_part("box")
    assert shape.face_count == meta.get("face_count", 6)


def test_box_topology_graph():
    shape, _ = _load_part("box")
    graph = build_topology_graph(shape)
    assert graph.face_count == 6
    assert graph.edge_count == 12


def test_box_tessellation():
    shape, _ = _load_part("box")
    mesh = tessellate(shape, tolerance_mm=0.5)
    assert len(mesh.triangles) >= 12
    assert len(mesh.vertices) >= 8


def test_cylinder_loads():
    shape, meta = _load_part("cylinder")
    assert shape.face_count == meta.get("face_count", 3)


def test_cylinder_tessellates():
    shape, _ = _load_part("cylinder")
    mesh = tessellate(shape, tolerance_mm=0.1)
    assert len(mesh.triangles) > 100  # lots of facets on the cylinder


def test_sphere_loads():
    shape, _ = _load_part("sphere")
    assert shape.face_count >= 1


def test_cone_loads():
    shape, _ = _load_part("cone")
    assert shape.face_count >= 2


def test_torus_loads():
    shape, _ = _load_part("torus")
    assert shape.face_count >= 1


def test_l_bracket_fused_geometry():
    shape, meta = _load_part("l_bracket")
    assert shape.face_count == meta.get("face_count")
    assert shape.face_count > 0


def test_stepped_shaft_loads():
    shape, meta = _load_part("stepped_shaft")
    assert shape.face_count == meta.get("face_count")


def test_fillet_test_loads():
    shape, meta = _load_part("fillet_test")
    assert shape.face_count == meta.get("face_count")


def test_cylinder_extract_smooth_edge():
    """The cylinder top/bottom face has a smooth circular edge."""
    shape, _ = _load_part("cylinder")
    for fi in range(shape.face_count):
        samples = sample_edge_chain_from_shape(shape, spacing=1.0, face_index=fi)
        if samples.sample_count > 0:
            assert all(
                abs(math.sqrt(s.tangent[0] ** 2 + s.tangent[1] ** 2 + s.tangent[2] ** 2) - 1.0) < 0.01
                for s in samples.samples
            ), f"Face {fi} has non-unit tangents"
            break


def test_stepped_shaft_extract_edge():
    """Stepped shaft has both cylindrical and planar faces."""
    shape, _ = _load_part("stepped_shaft")
    total_samples = 0
    for fi in range(shape.face_count):
        samples = sample_edge_chain_from_shape(shape, spacing=2.0, face_index=fi)
        total_samples += samples.sample_count
    assert total_samples > 0
