"""FreeCAD-only adapters.

Importing the core package never imports FreeCAD.  This adapter is the only
layer allowed to hold TopoShape values, and it converts them to immutable domain
records before returning.
"""

from .selection import (
    extract_feature_loop_from_selection,
    extract_feature_loop_from_shapes,
)
from .wire import extract_wire_loop_from_selection
from .face import extract_face_region_from_selection

__all__ = [
    "extract_feature_loop_from_selection",
    "extract_feature_loop_from_shapes",
    "extract_wire_loop_from_selection",
    "extract_face_region_from_selection",
]
