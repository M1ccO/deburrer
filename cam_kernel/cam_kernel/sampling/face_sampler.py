"""Face sampler — grid samples on selected faces.

Generates 2D grid samples on face regions for surface finishing
operations.  Each sample carries position, surface normal, and
parameter-space coordinates.

Used by:
- Ball-nose surface finishing (zigzag / spiral paths)
- Face normal extraction for tool-axis seeding
- Contact-point offset computation

TODO:
 - OCP-backed UV sampling using ``BRepAdaptor_Surface``
 - Adaptive stepover based on curvature and scallop height
 - Boundary-offset and island avoidance
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class FaceSample:
    position: Vec3
    normal: Vec3
    u: float
    v: float
    face_id: str


@dataclass(frozen=True)
class FaceGrid:
    id: str
    samples: Tuple[Tuple[FaceSample, ...], ...]
    face_ids: Tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.samples)

    @property
    def total_points(self) -> int:
        return sum(len(row) for row in self.samples)


def sample_face_region(graph, region, spacing: float = 1.0, direction: str = "auto") -> FaceGrid:
    """Sample a face region on a 2D grid using OCCT.

    TODO: OCP implementation.
    """
    raise NotImplementedError("Face sampling requires cadquery-ocp")


def sample_face_from_shape(
    shape,
    face_index: int,
    stepover: float,
    sample_spacing: float,
    direction: str = "auto",
) -> FaceGrid:
    """Sample one explicitly selected OCCT face into trimmed zigzag rows."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import (
        TopAbs_FACE,
        TopAbs_IN,
        TopAbs_ON,
        TopAbs_REVERSED,
    )
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Pnt2d, gp_Vec

    if stepover <= 0.0 or sample_spacing <= 0.0:
        raise ValueError("Face stepover and sample spacing must be positive.")
    raw = shape._shape if hasattr(shape, "_shape") else shape
    faces = []
    explorer = TopExp_Explorer(raw, TopAbs_FACE)
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    if face_index < 0 or face_index >= len(faces):
        raise ValueError("Selected face index is outside the STEP topology.")

    face = faces[face_index]
    adaptor = BRepAdaptor_Surface(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)
    if not all(math.isfinite(value) for value in (u_min, u_max, v_min, v_max)):
        raise ValueError("Selected face has an unbounded parameter domain.")

    def point_at(u_value, v_value):
        point = gp_Pnt()
        adaptor.D0(u_value, v_value, point)
        return (point.X(), point.Y(), point.Z())

    def inside(u_value, v_value):
        classifier = BRepClass_FaceClassifier(
            face,
            gp_Pnt2d(u_value, v_value),
            1.0e-7,
        )
        return classifier.State() in (TopAbs_IN, TopAbs_ON)

    def parametric_length(path_direction, fixed, steps=80):
        points = []
        for index in range(steps + 1):
            fraction = index / steps
            if path_direction == "u":
                u_value = u_min + (u_max - u_min) * fraction
                v_value = fixed
            else:
                u_value = fixed
                v_value = v_min + (v_max - v_min) * fraction
            if inside(u_value, v_value):
                points.append(point_at(u_value, v_value))
        return sum(
            math.dist(previous, current)
            for previous, current in zip(points, points[1:])
        )

    u_mid = 0.5 * (u_min + u_max)
    v_mid = 0.5 * (v_min + v_max)
    u_length = parametric_length("u", v_mid)
    v_length = parametric_length("v", u_mid)
    requested = str(direction or "auto").lower()
    if requested in ("u", "v"):
        path_direction = requested
    elif requested in ("x", "y", "z"):
        target_index = {"x": 0, "y": 1, "z": 2}[requested]
        du = gp_Vec()
        dv = gp_Vec()
        point = gp_Pnt()
        adaptor.D1(u_mid, v_mid, point, du, dv)
        u_vector = (du.X(), du.Y(), du.Z())
        v_vector = (dv.X(), dv.Y(), dv.Z())
        u_norm = max(math.sqrt(sum(value * value for value in u_vector)), 1.0e-12)
        v_norm = max(math.sqrt(sum(value * value for value in v_vector)), 1.0e-12)
        path_direction = (
            "u"
            if abs(u_vector[target_index]) / u_norm
            >= abs(v_vector[target_index]) / v_norm
            else "v"
        )
    elif requested == "auto":
        path_direction = "u" if u_length >= v_length else "v"
    else:
        raise ValueError("Face direction must be auto, X, Y, Z, U, or V.")

    cross_length = v_length if path_direction == "u" else u_length
    path_length = u_length if path_direction == "u" else v_length
    cross_count = max(2, int(math.ceil(cross_length / stepover)) + 1)
    path_count = max(3, int(math.ceil(path_length / sample_spacing)) + 1)
    rows = []
    face_id = "face_{}".format(face_index)

    for cross_index in range(cross_count):
        cross_fraction = cross_index / (cross_count - 1)
        current = []
        for path_index in range(path_count):
            path_fraction = path_index / (path_count - 1)
            if path_direction == "u":
                u_value = u_min + (u_max - u_min) * path_fraction
                v_value = v_min + (v_max - v_min) * cross_fraction
            else:
                u_value = u_min + (u_max - u_min) * cross_fraction
                v_value = v_min + (v_max - v_min) * path_fraction
            if not inside(u_value, v_value):
                if len(current) >= 2:
                    rows.append(tuple(current))
                current = []
                continue
            point = gp_Pnt()
            du = gp_Vec()
            dv = gp_Vec()
            adaptor.D1(u_value, v_value, point, du, dv)
            normal_vector = du.Crossed(dv)
            length = normal_vector.Magnitude()
            if length <= 1.0e-12:
                continue
            normal = (
                normal_vector.X() / length,
                normal_vector.Y() / length,
                normal_vector.Z() / length,
            )
            if face.Orientation() == TopAbs_REVERSED:
                normal = tuple(-value for value in normal)
            current.append(
                FaceSample(
                    position=(point.X(), point.Y(), point.Z()),
                    normal=normal,
                    u=u_value,
                    v=v_value,
                    face_id=face_id,
                )
            )
        if len(current) >= 2:
            rows.append(tuple(current))

    if not rows:
        raise ValueError("Selected face did not produce any valid finishing rows.")
    return FaceGrid(
        id=face_id,
        samples=tuple(rows),
        face_ids=(face_id,),
    )
