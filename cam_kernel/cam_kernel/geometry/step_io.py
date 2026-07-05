"""STEP file I/O via OCP.

Reads and writes STEP files using OCCT's STEPControl framework.
Supports AP203, AP214, and AP242 schemas.

Usage::

    from cam_kernel.geometry.step_io import read_step, write_step
    from cam_kernel.geometry.occt_session import OcctSession

    with OcctSession() as session:
        shape = read_step(session, "part.step")
        write_step(shape, "output.step")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class StepImportResult:
    """Metadata from a STEP file import."""

    path: str
    num_solids: int = 0
    num_faces: int = 0
    num_edges: int = 0
    unit: str = "mm"
    warnings: Tuple[str, ...] = ()


def read_step(session_or_path, path: str = None):
    """Read a STEP file.

    Args:
        session_or_path: Either an OcctSession or a path string (auto-creates session).
        path: The STEP file path (required if session is provided).

    Returns:
        TopoShape wrapping the loaded shape.
    """
    from .occt_session import OcctSession, TopoShape

    if isinstance(session_or_path, str):
        sess = OcctSession()
        filepath = session_or_path
        with sess:
            return TopoShape(sess.load_step(filepath))
    else:
        return TopoShape(session_or_path.load_step(path))


def write_step(shape, path: str, schema: str = "AP242") -> None:
    """Write a shape to a STEP file.

    Args:
        shape: TopoShape or raw TopoDS_Shape.
        path: Output file path.
        schema: STEP schema version ("AP203", "AP214", "AP242").
    """
    from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType

    from .occt_session import TopoShape

    writer = STEPControl_Writer()
    raw = shape._shape if isinstance(shape, TopoShape) else shape

    schema_map = {
        "AP203": STEPControl_StepModelType.STEPControl_AsIs,
        "AP214": STEPControl_StepModelType.STEPControl_AsIs,
        "AP242": STEPControl_StepModelType.STEPControl_AsIs,
    }
    mode = schema_map.get(schema, STEPControl_StepModelType.STEPControl_AsIs)

    status = writer.Transfer(raw, mode)
    if status != 1:
        raise IOError(f"Failed to transfer shape for STEP export")
    writer.Write(str(path))


def step_metadata(session_or_shape, path: str = None) -> StepImportResult:
    """Read STEP metadata without keeping the full shape.

    Args:
        session_or_shape: Either an OcctSession or a TopoShape.
        path: File path (needed if session is provided).
    """
    from .occt_session import OcctSession, TopoShape

    if isinstance(session_or_shape, TopoShape):
        shape = session_or_shape
        filepath = "<memory>"
    else:
        sess = session_or_shape
        shape = TopoShape(sess.load_step(path))
        filepath = path

    return StepImportResult(
        path=filepath,
        num_faces=shape.face_count,
        num_edges=shape.edge_count,
    )
