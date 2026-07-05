from __future__ import annotations

import math

from ..domain.errors import GeometryError
from ..domain.models import Vec3

EPSILON = 1.0e-10


def add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def scale(a: Vec3, factor: float) -> Vec3:
    return a[0] * factor, a[1] * factor, a[2] * factor


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3, label: str = "vector") -> Vec3:
    magnitude = length(a)
    if magnitude <= EPSILON:
        raise GeometryError("%s has zero length" % label)
    return scale(a, 1.0 / magnitude)


def project_onto_plane(vector: Vec3, plane_normal: Vec3) -> Vec3:
    normal = normalize(plane_normal)
    return sub(vector, scale(normal, dot(vector, normal)))


def angle_deg(a: Vec3, b: Vec3) -> float:
    aa = normalize(a)
    bb = normalize(b)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(aa, bb)))))


def rotate_about_axis(vector: Vec3, axis: Vec3, angle_deg_value: float) -> Vec3:
    """Rodrigues rotation."""

    unit_axis = normalize(axis, "rotation axis")
    radians = math.radians(angle_deg_value)
    c = math.cos(radians)
    s = math.sin(radians)
    return add(
        add(scale(vector, c), scale(cross(unit_axis, vector), s)),
        scale(unit_axis, dot(unit_axis, vector) * (1.0 - c)),
    )


def midpoint(a: Vec3, b: Vec3) -> Vec3:
    return scale(add(a, b), 0.5)
