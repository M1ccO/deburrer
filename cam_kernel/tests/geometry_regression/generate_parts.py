"""Generate regression test STEP files via OCCT.

Creates a suite of test parts with known topology and saves them as
STEP files in ``tests/geometry_regression/parts/``.

Run as::

    python tests/geometry_regression/generate_parts.py

Each part includes a face/edge metadata file that documents the
expected counts for the regression test suite.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from project root
# Path: tests/geometry_regression/generate_parts.py -> project root
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeTorus,
)
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.gp import gp_Vec, gp_Trsf
from OCP.TopoDS import TopoDS
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE

from cam_kernel.cam_kernel.geometry.occt_session import OcctSession, TopoShape
from cam_kernel.cam_kernel.geometry.step_io import write_step


OUT_DIR = Path(__file__).resolve().parent / "parts"
OUT_DIR.mkdir(exist_ok=True)


def _save(name: str, shape, metadata: dict) -> None:
    """Save a shape to STEP and write metadata JSON."""
    step_path = OUT_DIR / f"{name}.step"
    meta_path = OUT_DIR / f"{name}.json"
    write_step(shape, str(step_path))
    metadata["file"] = str(step_path.name)
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  {name}.step: faces={metadata.get('face_count', '?')}, edges={metadata.get('edge_count', '?')}")


def gen_box() -> None:
    """30 x 20 x 10 mm box."""
    with OcctSession() as sess:
        shape = sess.make_box(30.0, 20.0, 10.0)
        _save("box", shape, {
            "kind": "box",
            "face_count": shape.face_count,
            "edge_count": shape.edge_count,
            "dimensions": [30, 20, 10],
            "expected_geometry": {"planes": 6, "cylinders": 0, "cones": 0},
        })


def gen_cylinder() -> None:
    """Cylinder, radius 15, height 10."""
    with OcctSession() as sess:
        shape = sess.make_cylinder(15.0, 10.0)
        _save("cylinder", shape, {
            "kind": "cylinder",
            "face_count": shape.face_count,
            "edge_count": shape.edge_count,
            "dimensions": {"radius": 15, "height": 10},
            "expected_geometry": {"planes": 2, "cylinders": 1},
        })


def gen_torus() -> None:
    """Torus: major radius 30, minor radius 10."""
    torus = BRepPrimAPI_MakeTorus(30.0, 10.0).Shape()
    ts = TopoShape(torus)
    _save("torus", ts, {
        "kind": "torus",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "dimensions": {"major_r": 30, "minor_r": 10},
        "expected_geometry": {"tori": 1, "planes": 0},
    })


def gen_l_bracket() -> None:
    """L-shaped bracket: two boxes joined."""
    box1 = BRepPrimAPI_MakeBox(60.0, 10.0, 30.0).Shape()
    box2 = BRepPrimAPI_MakeBox(10.0, 60.0, 30.0).Shape()
    fuse = BRepAlgoAPI_Fuse(box1, box2)
    fuse.Build()
    ts = TopoShape(fuse.Shape())
    _save("l_bracket", ts, {
        "kind": "l_bracket",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "note": "Two boxes fused into L-shape",
    })


def gen_stepped_shaft() -> None:
    """Stepped shaft: two cylinders of different diameters stacked."""
    big = BRepPrimAPI_MakeCylinder(20.0, 30.0).Shape()
    small = BRepPrimAPI_MakeCylinder(15.0, 20.0).Shape()
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(0, 0, 30))
    small_t = BRepBuilderAPI_Transform(small, trsf, True).Shape()
    fuse = BRepAlgoAPI_Fuse(big, small_t)
    fuse.Build()
    ts = TopoShape(fuse.Shape())
    _save("stepped_shaft", ts, {
        "kind": "stepped_shaft",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "note": "Cylinder stack — typical lathe part",
    })


def gen_fillet_test() -> None:
    """Box with fillet on all 12 edges — tests fillet topology."""
    box = BRepPrimAPI_MakeBox(20.0, 20.0, 10.0).Shape()
    fillet = BRepFilletAPI_MakeFillet(box)
    exp = TopExp_Explorer(box, TopAbs_EDGE)
    while exp.More():
        edge = TopoDS.Edge_s(exp.Current())
        fillet.Add(2.0, edge)
        exp.Next()
    fillet.Build()
    filleted = fillet.Shape() if fillet.IsDone() else box
    ts = TopoShape(filleted)
    _save("fillet_test", ts, {
        "kind": "fillet_test",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "note": "Box with fillet on all 12 edges",
    })


def gen_sphere() -> None:
    """Sphere radius 20."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    sphere = BRepPrimAPI_MakeSphere(20.0).Shape()
    ts = TopoShape(sphere)
    _save("sphere", ts, {
        "kind": "sphere",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "dimensions": {"radius": 20},
        "expected_geometry": {"spheres": 1, "planes": 0},
    })


def gen_cone() -> None:
    """Cone radius 15, height 30."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
    cone = BRepPrimAPI_MakeCone(15.0, 0.0, 30.0).Shape()
    ts = TopoShape(cone)
    _save("cone", ts, {
        "kind": "cone",
        "face_count": ts.face_count,
        "edge_count": ts.edge_count,
        "dimensions": {"radius": 15, "height": 30},
        "expected_geometry": {"planes": 1, "cones": 1},
    })


def main() -> None:
    print(f"Generating regression STEP parts in {OUT_DIR}/")
    generators = [
        ("box", gen_box),
        ("cylinder", gen_cylinder),
        ("cone", gen_cone),
        ("sphere", gen_sphere),
        ("torus", gen_torus),
        ("l_bracket", gen_l_bracket),
        ("stepped_shaft", gen_stepped_shaft),
        ("fillet_test", gen_fillet_test),
    ]
    for name, gen in generators:
        print(f"\n{name}:")
        try:
            gen()
        except Exception as e:
            print(f"  FAILED: {e}")
    print(f"\nDone. Files in {OUT_DIR}/")
    step_files = list(OUT_DIR.glob("*.step"))
    meta_files = list(OUT_DIR.glob("*.json"))
    print(f"  STEP: {len(step_files)} files")
    print(f"  JSON: {len(meta_files)} metadata files")


if __name__ == "__main__":
    main()
