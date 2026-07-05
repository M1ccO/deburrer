import struct
from pathlib import Path

import pytest

from fc_deburr.preview.models import PreviewDocument, PreviewPolyline, PreviewToolGeometry
from fc_deburr.ui.main_window import _display_stl_path
from fc_deburr.ui.web_preview.payload import build_payload
from fc_deburr.ui.web_preview.stl import read_binary_stl


def test_payload_contains_expected_keys():
    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
    )
    payload = build_payload(doc)
    expected = {
        "spindle", "polylines", "vectors", "markers",
        "tool", "toolPoses", "warnings", "workpiece", "bounds",
    }
    assert set(payload.keys()) >= expected
    assert payload["workpiece"] is None
    assert payload["tool"] is None


def test_payload_polylines_match_document():
    poly = PreviewPolyline(
        name="Source edge",
        points=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        color="#00d7ff",
        closed=True,
    )
    doc = PreviewDocument(
        polylines=(poly,),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
    )
    payload = build_payload(doc)
    assert len(payload["polylines"]) == 1
    assert payload["polylines"][0]["name"] == "Source edge"
    assert payload["polylines"][0]["color"] == "#00d7ff"
    assert payload["polylines"][0]["closed"] is True
    assert payload["polylines"][0]["points"] == [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]


def test_payload_bounds_from_polylines():
    poly = PreviewPolyline(
        name="Cutter reference",
        points=((5.0, 2.0, 1.0), (15.0, 8.0, 3.0)),
        color="#ffd23f",
    )
    doc = PreviewDocument(
        polylines=(poly,),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
    )
    payload = build_payload(doc)
    bounds = payload["bounds"]
    assert bounds[0] == [5.0, 2.0, 1.0]
    assert bounds[1] == [15.0, 8.0, 3.0]


def test_payload_spindle_from_document():
    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
        spindle_origin=(1.0, 2.0, 3.0),
        spindle_axis=(0.0, 0.0, 1.0),
    )
    payload = build_payload(doc)
    assert payload["spindle"] == {
        "origin": [1.0, 2.0, 3.0],
        "axis": [0.0, 0.0, 1.0],
    }


def test_payload_tool_does_not_crash_on_none():
    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
    )
    payload = build_payload(doc)
    assert payload["tool"] is None


def test_payload_includes_cutting_length():
    tool = PreviewToolGeometry(
        kind="ball",
        diameter=6.0,
        stickout=25.0,
        cutting_length=15.0,
        included_angle_deg=None,
        tip_flat_diameter=0.0,
        tip_radius=0.0,
    )
    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
        tool=tool,
    )
    payload = build_payload(doc)
    assert payload["tool"] is not None
    assert payload["tool"]["cuttingLength"] == 15.0


def test_payload_cutting_length_default_zero():
    tool = PreviewToolGeometry(
        kind="ball",
        diameter=6.0,
        stickout=25.0,
        cutting_length=0.0,
        included_angle_deg=None,
        tip_flat_diameter=0.0,
        tip_radius=0.0,
    )
    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
        tool=tool,
    )
    payload = build_payload(doc)
    assert payload["tool"]["cuttingLength"] == 0.0


def test_stl_reader_returns_triangles_and_normals(tmp_path):
    stl = tmp_path / "test.stl"
    header = b"\x00" * 80
    count = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0.0, 0.0, 1.0)
    v0 = struct.pack("<fff", 0.0, 0.0, 0.0)
    v1 = struct.pack("<fff", 1.0, 0.0, 0.0)
    v2 = struct.pack("<fff", 0.0, 1.0, 0.0)
    attr = b"\x00\x00"
    stl.write_bytes(header + count + normal + v0 + v1 + v2 + attr)

    triangles, normals = read_binary_stl(str(stl))
    assert len(triangles) == 1
    assert len(normals) == 1
    assert triangles[0] == (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    assert normals[0] == (0.0, 0.0, 1.0)


def test_payload_with_stl(tmp_path):
    stl = tmp_path / "workpiece.stl"
    header = b"\x00" * 80
    count = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0.0, 0.0, 1.0)
    v0 = struct.pack("<fff", 0.0, 0.0, 0.0)
    v1 = struct.pack("<fff", 2.0, 0.0, 0.0)
    v2 = struct.pack("<fff", 0.0, 2.0, 0.0)
    attr = b"\x00\x00"
    stl.write_bytes(header + count + normal + v0 + v1 + v2 + attr)

    doc = PreviewDocument(
        polylines=(),
        vectors=(),
        markers=(),
        b_values=(),
        c_values=(),
    )
    payload = build_payload(doc, str(stl))
    assert payload["workpiece"] is not None
    assert len(payload["workpiece"]["positions"]) == 9  # 3 verts * 3 coords
    assert len(payload["workpiece"]["normals"]) == 9


def test_newer_lighter_meshed_export_is_selected(tmp_path):
    feature = tmp_path / "feature.json"
    exact = tmp_path / "feature.stl"
    lighter = tmp_path / "Part (Meshed).stl"
    feature.write_text("{}", encoding="utf-8")
    exact.write_bytes(b"x" * 100)
    lighter.write_bytes(b"x" * 25)
    exact.touch()
    lighter.touch()

    assert _display_stl_path(feature) == lighter
