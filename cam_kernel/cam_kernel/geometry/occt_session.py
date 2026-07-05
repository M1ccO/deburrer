"""OCCT session management via OCP (cadquery-ocp).

Provides a managed session for loading STEP files, building topology
graphs, tessellating shapes, and extracting geometric properties.

Usage::

    with OcctSession() as session:
        shape = session.load_step("part.step")
        graph = session.build_topology_graph(shape)
        mesh = session.tessellate(shape, tolerance=0.1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class OcctSession:
    """Managed OCCT session."""

    auto_close: bool = True

    def __enter__(self) -> "OcctSession":
        return self

    def __exit__(self, *args) -> None:
        pass

    def load_step(self, path: str) -> "TopoShape":
        """Load a STEP file, return a TopoShape."""
        from OCP.STEPControl import STEPControl_Reader
        from OCP.Interface import Interface_Static

        reader = STEPControl_Reader()
        status = reader.ReadFile(str(path))
        if status != 1:  # IFSelect_RetDone
            raise IOError(f"Failed to read STEP file: {path}")
        reader.TransferRoots()
        return TopoShape(reader.OneShape())

    @staticmethod
    def load_brep(brep_string: str):
        """Parse a BREP string into a shape."""
        raise NotImplementedError("BREP parsing not yet implemented")

    @staticmethod
    def compound(shapes) -> "TopoShape":
        """Combine shapes into a compound."""
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Builder
        from OCP.TopAbs import TopAbs_COMPOUND

        compound = TopoDS.Compound_s()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        for shape in shapes:
            builder.Add(compound, shape.Shape() if isinstance(shape, TopoShape) else shape)
        return TopoShape(compound)

    @staticmethod
    def make_box(dx: float, dy: float, dz: float) -> "TopoShape":
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        return TopoShape(BRepPrimAPI_MakeBox(dx, dy, dz).Shape())

    @staticmethod
    def make_cylinder(r: float, h: float) -> "TopoShape":
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        return TopoShape(BRepPrimAPI_MakeCylinder(r, h).Shape())


class TopoShape:
    """Wrapper for an OCCT TopoDS_Shape with convenience methods."""

    def __init__(self, shape):
        from OCP.TopoDS import TopoDS_Shape

        if isinstance(shape, TopoDS_Shape):
            self._shape = shape
        else:
            self._shape = shape

    def shape(self):
        return self._shape

    @property
    def face_count(self) -> int:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE

        exp = TopExp_Explorer(self._shape, TopAbs_FACE)
        count = 0
        while exp.More():
            count += 1
            exp.Next()
        return count

    @property
    def edge_count(self) -> int:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE

        exp = TopExp_Explorer(self._shape, TopAbs_EDGE)
        count = 0
        while exp.More():
            count += 1
            exp.Next()
        return count

    def bbox(self) -> Tuple[float, float, float, float, float, float]:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        bbox = Bnd_Box()
        BRepBndLib.Add_s(self._shape, bbox)
        return bbox.Get()
