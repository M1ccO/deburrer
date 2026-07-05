"""Debug export — serialized geometry and path export.

Exports kernel-internal data for external tools:
- JSON point clouds (positions, normals, axes)
- CSV for spreadsheet analysis
- VTK for ParaView inspection
- GLTF for web-based 3D viewing

Useful for debugging, regression testing, and manual inspection
without needing FreeCAD or the 3D viewer.

TODO:
 - VTK unstructured grid export
 - GLTF mesh + polyline export
 - HTML report with embedded Three.js viewer
"""

from __future__ import annotations

import json
from typing import Any, Dict, List


def export_points_json(points: List[Any], path: str) -> None:
    """Export a list of points as a JSON file."""
    data = []
    for pt in points:
        if hasattr(pt, "__dict__"):
            data.append({k: v for k, v in pt.__dict__.items() if not k.startswith("_")})
        else:
            data.append(pt)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, default=str)


def export_csv(points: List[Any], path: str) -> None:
    """Export points as CSV with columns for position, axis, B, C."""
    import csv

    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["x", "y", "z", "ax", "ay", "az", "b_deg", "c_deg", "motion"])
        for pt in points:
            writer.writerow([
                pt.xyz[0] if hasattr(pt, "xyz") else "",
                pt.xyz[1] if hasattr(pt, "xyz") else "",
                pt.xyz[2] if hasattr(pt, "xyz") else "",
                pt.tool_axis[0] if hasattr(pt, "tool_axis") else "",
                pt.tool_axis[1] if hasattr(pt, "tool_axis") else "",
                pt.tool_axis[2] if hasattr(pt, "tool_axis") else "",
                pt.b_deg if hasattr(pt, "b_deg") else "",
                pt.c_deg if hasattr(pt, "c_deg") else "",
                pt.motion.value if hasattr(pt, "motion") and hasattr(pt.motion, "value") else "",
            ])
