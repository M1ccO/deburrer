"""Visualization layer — debug export and backplot.

Provides renderer-neutral visualization data for debugging and
development.  Not used for production NC output.

- ``backplot.py`` — 2D backplot data (top-down, optional B/C traces)
- ``debug_export.py`` — VTK/GLTF/serialized geometry export

The viz layer is deliberately minimal — the existing ``fc_deburr.ui``
package (Three.js viewer, 2D backplot, B/C plot) provides rich
interactive visualization for FreeCAD.  This layer provides the
standalone equivalents for headless/CLI use.

TODO:
 - Headless PNG/SVG backplot generation (matplotlib)
 - Debug VTK export for ParaView inspection
 - JSON-based wireframe export for external viewers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

Vec3 = Tuple[float, float, float]


@dataclass
class BackplotData:
    source_points: List[Vec3]
    contact_points: List[Vec3]
    cutter_ref_points: List[Vec3]
    tool_axes: List[Vec3]
    b_values: List[float]
    c_values: List[float]
    motion_kinds: List[str]


def collect_backplot_data(toolpath) -> BackplotData:
    """Extract backplot arrays from a toolpath.

    TODO: Implement full extraction from validated toolpath.
    """
    return BackplotData(
        source_points=[],
        contact_points=[],
        cutter_ref_points=[],
        tool_axes=[],
        b_values=[],
        c_values=[],
        motion_kinds=[],
    )
