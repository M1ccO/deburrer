from __future__ import annotations

import json
from typing import Any, Optional

from ...preview.models import PreviewDocument
from .stl import read_binary_stl


def build_json(document: PreviewDocument,
               stl_path: Optional[str] = None) -> str:
    payload = build_payload(document, stl_path)
    return json.dumps(payload)


def build_payload(document: PreviewDocument,
                  stl_path: Optional[str] = None) -> dict:
    payload: dict[str, Any] = {}

    payload["spindle"] = {
        "origin": list(document.spindle_origin),
        "axis": list(document.spindle_axis),
    }

    payload["polylines"] = [
        {
            "name": line.name,
            "color": line.color,
            "closed": line.closed,
            "dashed": line.dashed,
            "points": [list(p) for p in line.points],
        }
        for line in document.polylines
    ]

    payload["vectors"] = [
        {
            "start": list(vec.start),
            "end": list(vec.end),
            "color": vec.color,
        }
        for vec in document.vectors
    ]

    payload["markers"] = [
        {
            "name": m.name,
            "position": list(m.position),
            "color": m.color,
        }
        for m in document.markers
    ]

    if document.tool:
        payload["tool"] = {
            "kind": document.tool.kind,
            "diameter": document.tool.diameter,
            "stickout": document.tool.stickout,
            "cuttingLength": document.tool.cutting_length,
            "includedAngleDeg": document.tool.included_angle_deg,
            "tipFlatDiameter": document.tool.tip_flat_diameter,
            "tipRadius": document.tool.tip_radius,
        }
    else:
        payload["tool"] = None

    payload["toolPoses"] = [
        {
            "cutterReference": list(p.cutter_reference),
            "toolAxis": list(p.tool_axis),
            "toolAxisBOnly": list(p.tool_axis_b_only),
            "motion": p.motion.value,
            "bDeg": p.b_deg,
            "cDeg": p.c_deg,
            "partRotationDeg": p.part_rotation_deg,
        }
        for p in document.tool_poses
    ]

    payload["warnings"] = list(document.warnings)

    if stl_path is not None:
        triangles, normals = read_binary_stl(stl_path)
        positions = []
        face_normals = []
        for tri, nrm in zip(triangles, normals):
            for vertex in tri:
                positions.extend(vertex)
            face_normals.extend(nrm)
            face_normals.extend(nrm)
            face_normals.extend(nrm)
        payload["workpiece"] = {
            "positions": positions,
            "normals": face_normals,
        }
    else:
        payload["workpiece"] = None

    all_pts: list[float] = []
    for line in document.polylines:
        for pt in line.points:
            all_pts.extend(pt)
    if all_pts:
        xs = all_pts[0::3]
        ys = all_pts[1::3]
        zs = all_pts[2::3]
        payload["bounds"] = [
            [min(xs), min(ys), min(zs)],
            [max(xs), max(ys), max(zs)],
        ]
    else:
        payload["bounds"] = [[-50, -50, -50], [50, 50, 50]]

    return payload
