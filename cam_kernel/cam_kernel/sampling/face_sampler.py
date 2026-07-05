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
