"""Run with FreeCAD's bundled Python, not the normal pytest interpreter."""

import math
import os
import sys
import tempfile

import FreeCAD as App
import Part

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fc_deburr.application.pipeline import calculate_toolpath
from fc_deburr.application.face_pipeline import calculate_face_toolpath
from fc_deburr.domain.models import Operation, ToolDefinition, ToolKind
from fc_deburr.domain.serialization import (
    load_feature,
    load_feature_loop,
    save_face_region,
    save_feature_loop,
)
from fc_deburr.freecad_adapter.face import extract_face_region_from_selection
from fc_deburr.freecad_adapter.selection import (
    extract_feature_loop_from_selection,
    extract_feature_loop_from_shapes,
)
from fc_deburr.freecad_adapter.wire import extract_wire_loop_from_selection
from fc_deburr.machine.profiles import MachineProfile


def main():
    shape = Part.makeCylinder(10.0, 10.0)
    top_edge = shape.Edges[0]
    guide_face = shape.Faces[1]
    start_vertex = top_edge.firstVertex()

    loop = extract_feature_loop_from_shapes(
        parent_shape=shape,
        selected_edges=[top_edge],
        guide_face=guide_face,
        start_vertex=start_vertex,
        sample_spacing=2.5,
        feature_id="cylinder_top",
        source_object_id="Cylinder",
        edge_ids=("Edge1",),
        guide_face_id="Face2",
        c0_vertex_id="Vertex1",
    )
    assert loop.closed
    assert len(loop.samples) >= 25
    assert _close(loop.samples[0].position, (10.0, 0.0, 10.0), 1.0e-5)
    assert _close(loop.samples[0].guide_normal, (0.0, 0.0, 1.0), 1.0e-5)
    assert _close(loop.samples[0].other_normal, (1.0, 0.0, 0.0), 1.0e-5)
    assert loop.samples[0].source_edge_id == "Edge1"
    reversed_loop = extract_feature_loop_from_shapes(
        parent_shape=shape,
        selected_edges=[top_edge],
        guide_face=guide_face,
        start_vertex=start_vertex,
        sample_spacing=2.5,
        reverse=True,
    )
    assert _close(reversed_loop.samples[0].position, loop.samples[0].position, 1.0e-5)
    assert reversed_loop.samples[1].position[1] * loop.samples[1].position[1] < 0.0

    class Source:
        Name = "Cylinder"
        Shape = shape

    class Selection:
        Object = Source()
        SubElementNames = ("Edge1", "Face2", "Vertex1")
        SubObjects = (top_edge, guide_face, start_vertex)

    selected_loop = extract_feature_loop_from_selection(
        [Selection()], sample_spacing=2.5
    )
    assert selected_loop.source_object_id == "Cylinder"
    assert selected_loop.source_edge_ids == ("Edge1",)
    assert selected_loop.guide_face_id == "Face2"
    assert selected_loop.c0_vertex_id == "Vertex1"

    copied_loop = extract_feature_loop_from_shapes(
        parent_shape=shape,
        selected_edges=[top_edge.copy()],
        guide_face=guide_face.copy(),
        start_vertex=start_vertex.copy(),
        sample_spacing=2.5,
        edge_ids=("Edge1",),
        guide_face_id="Face2",
        c0_vertex_id="Vertex1",
    )
    assert len(copied_loop.samples) == len(loop.samples)
    assert copied_loop.samples[0].source_edge_id == "Edge1"

    disk_edge = Part.makeCircle(10.0)
    disk = Part.Face(Part.Wire([disk_edge]))
    disk_loop = extract_feature_loop_from_shapes(
        parent_shape=disk,
        selected_edges=[disk.Edges[0]],
        guide_face=disk,
        start_vertex=disk.Edges[0].firstVertex(),
        sample_spacing=2.5,
        edge_ids=("Edge1",),
        guide_face_id="Face1",
        c0_vertex_id="Vertex1",
    )
    assert _close(disk_loop.samples[0].guide_normal, (0.0, 0.0, 1.0), 1.0e-5)
    assert _close(disk_loop.samples[0].other_normal, (1.0, 0.0, 0.0), 1.0e-4)

    cylinder_side = shape.Faces[0].copy()
    side_top_edge = max(
        cylinder_side.Edges,
        key=lambda candidate: candidate.CenterOfMass.z,
    )
    curved_loop = extract_feature_loop_from_shapes(
        parent_shape=cylinder_side,
        selected_edges=[side_top_edge],
        guide_face=cylinder_side,
        start_vertex=side_top_edge.firstVertex(),
        sample_spacing=2.5,
    )
    assert _close(curved_loop.samples[0].guide_normal, (1.0, 0.0, 0.0), 1.0e-4)
    assert _close(curved_loop.samples[0].other_normal, (0.0, 0.0, 1.0), 1.0e-4)

    independent_circle = Part.makeCircle(10.0)
    independent_wire = Part.Wire([independent_circle])
    compound = Part.Compound([disk, independent_wire])
    standalone_edge = next(
        edge
        for edge in compound.Edges
        if not any(
            face_edge.isSame(edge)
            for face in compound.Faces
            for face_edge in face.Edges
        )
    )
    geometric_loop = extract_feature_loop_from_shapes(
        parent_shape=compound,
        selected_edges=[standalone_edge],
        guide_face=compound.Faces[0],
        start_vertex=standalone_edge.firstVertex(),
        sample_spacing=2.5,
    )
    assert _close(
        geometric_loop.samples[0].guide_normal,
        (0.0, 0.0, 1.0),
        1.0e-5,
    )
    assert _close(
        geometric_loop.samples[0].other_normal,
        (1.0, 0.0, 0.0),
        1.0e-4,
    )

    radial_edge = Part.makeCircle(
        10.0,
        App.Vector(0.0, 0.0, 0.0),
        App.Vector(1.0, 0.0, 0.0),
    )

    class WireSource:
        Name = "DeburrWire"
        Shape = Part.Wire([radial_edge])

    class WireSelection:
        Object = WireSource()
        SubElementNames = ("Edge1",)
        SubObjects = (radial_edge,)

    wire_loop = extract_wire_loop_from_selection(
        [WireSelection()],
        sample_spacing=2.5,
    )
    assert _close(wire_loop.center_xyz, (0.0, 0.0, 0.0), 0.05)
    assert wire_loop.samples[0].position[1] > 9.9
    assert wire_loop.c0_vertex_id == "CENTER_MAX_Y"
    assert abs(
        sum(
            wire_loop.samples[0].tangent[index]
            * wire_loop.samples[0].guide_normal[index]
            for index in range(3)
        )
    ) < 1.0e-6

    plane_face = Part.makePlane(10.0, 5.0)

    class FaceSource:
        Name = "FinishFace"
        Shape = plane_face

    class FaceSelection:
        Object = FaceSource()
        SubElementNames = ("Face1",)
        SubObjects = (plane_face,)

    face_region = extract_face_region_from_selection([FaceSelection()])
    assert len(face_region.patches) == 1
    handle, face_path = tempfile.mkstemp(suffix=".json")
    os.close(handle)
    try:
        save_face_region(face_path, face_region)
        restored_face = load_feature(face_path)
        assert restored_face.id == face_region.id
        assert len(restored_face.patches) == 1
    finally:
        os.remove(face_path)
    face_tool = ToolDefinition(
        id="B6",
        kind=ToolKind.BALL,
        diameter=6.0,
        stickout=25.0,
    )
    face_operation = Operation(
        id="finish",
        tool_id=face_tool.id,
        surface_tolerance=0.05,
        path_sample_spacing=0.5,
        safety_lift=2.0,
    )
    face_result = calculate_face_toolpath(
        face_region,
        face_tool,
        face_operation,
        MachineProfile(),
    )
    assert face_result.validation.ok
    assert "Face finishing:" in face_result.machine_path.warnings[0]
    assert sum(
        point.motion.value == "cut"
        for point in face_result.machine_path.points
    ) > 20

    handle, path = tempfile.mkstemp(suffix=".json")
    os.close(handle)
    try:
        save_feature_loop(path, loop)
        assert load_feature_loop(path) == loop
    finally:
        os.remove(path)

    tool = ToolDefinition(
        id="C90",
        kind=ToolKind.CHAMFER,
        diameter=6.0,
        stickout=25.0,
        included_angle_deg=90.0,
        contact_radius=0.5,
    )
    operation = Operation(
        id="C0.5",
        tool_id=tool.id,
        target_width=0.5,
    )
    result = calculate_toolpath(loop, tool, operation, MachineProfile())
    first_cut = next(point for point in result.machine_path.points if point.motion.value == "cut")
    assert abs(first_cut.c_deg) < 1.0e-8
    assert result.validation.ok
    print("FreeCAD integration check passed (%d feature samples)" % len(loop.samples))


def _close(actual, expected, tolerance):
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected))


if __name__ == "__main__":
    main()
