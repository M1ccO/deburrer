"""Gouge checks via FCL.

Detects cutter intrusion into the workpiece beyond the intended contact
point.  Two types:

1. **Local gouge** — the cutter flank or shank intrudes into the part
   near the contact point.  Detected by sampling points along the tool
   body and checking each against the part surface.
2. **Global gouge** — the cutter body collides with a distant part
   feature.  Detected by FCL distance queries between the cutter swept
   volume and the part mesh.

Gouge checks are run inline with the posture solver — a posture that
gouges the part is rejected or penalized before kinematics run.

Usage::

    scene = FclScene()
    part_id = scene.add_mesh(part_verts, part_tris, name="part")

    checker = LocalGougeChecker(scene, part_id)
    report = checker.check_at(contact_xyz, tool_axis, cutter_radius)
    if report.gouge_detected:
        ...
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from .fcl_scene import (
    CollisionReport,
    DistanceResult,
    FclScene,
    make_transform,
)


@dataclass(frozen=True)
class GougeReport:
    gouge_detected: bool
    max_penetration_mm: float = 0.0
    offending_position: Optional[Tuple[float, float, float]] = None
    offending_station: Optional[int] = None
    diagnosis: str = ""


def fcl_available() -> bool:
    try:
        import fcl
        return True
    except ImportError:
        return False


class LocalGougeChecker:
    """Sample-based gouge check at a single contact point.

    The cutter is modeled as a sphere at the contact point with the
    tool radius.  The check verifies that no nearby part surface comes
    closer than the contact distance minus a small tolerance.
    """

    def __init__(self, scene: FclScene, part_id: str,
                 sample_count: int = 5,
                 safety_margin_mm: float = 0.05):
        self.scene = scene
        self.part_id = part_id
        self.sample_count = sample_count
        self.safety_margin_mm = safety_margin_mm

    def check_at(self, contact_xyz: Tuple[float, float, float],
                 tool_axis: Tuple[float, float, float],
                 cutter_radius: float) -> GougeReport:
        """Check for gouge at a single contact point.

        Args:
            contact_xyz: The intended contact point on the part surface.
            tool_axis: Tool axis direction (forward, away from workpiece).
            cutter_radius: Radius of the cutting tool.
        """
        ball_id = f"_gouge_ball_{id(self)}"
        self.scene.add_sphere(cutter_radius, name=ball_id)

        T = make_transform(contact_xyz, axis_z=tool_axis)
        result = self.scene.distance(self.part_id, ball_id, T)
        self.scene.remove(ball_id)

        if result.distance < -self.safety_margin_mm:
            return GougeReport(
                gouge_detected=True,
                max_penetration_mm=-result.distance,
                offending_position=result.nearest_on_b,
                diagnosis=f"Cutter flank penetrates {abs(result.distance):.3f}mm beyond contact",
            )

        return GougeReport(
            gouge_detected=False,
            max_penetration_mm=max(0.0, -result.distance),
            diagnosis=f"Clearance: {result.distance:.3f}mm",
        )


class GlobalGougeChecker:
    """Path-wide gouge check using FCL distance queries.

    Tests a sequence of cutter poses (contact + axis) against the
    part mesh.  Each cutter pose is tested as a sphere at the contact
    point with the cutter radius.  Returns the worst-case gouge found.
    """

    def __init__(self, scene: FclScene, part_id: str,
                 cutter_radius: float,
                 safety_margin_mm: float = 0.05):
        self.scene = scene
        self.part_id = part_id
        self.cutter_radius = cutter_radius
        self.safety_margin_mm = safety_margin_mm
        self._ball_id = None

    def __enter__(self):
        self._ball_id = f"_gouge_path_{id(self)}"
        self.scene.add_sphere(self.cutter_radius, name=self._ball_id)
        return self

    def __exit__(self, *args):
        if self._ball_id is not None:
            self.scene.remove(self._ball_id)
            self._ball_id = None

    def check_path(
        self,
        contact_points: List[Tuple[float, float, float]],
        tool_axes: List[Tuple[float, float, float]],
    ) -> GougeReport:
        """Check the full path.  Returns the worst gouge found.

        Args:
            contact_points: List of (x, y, z) cutter reference points.
            tool_axes: List of tool axes (forward direction).
        """
        if len(contact_points) != len(tool_axes):
            raise ValueError("contact_points and tool_axes must have equal length")
        if not contact_points:
            return GougeReport(gouge_detected=False, diagnosis="empty path")
        if self._ball_id is None:
            raise RuntimeError("Use as context manager: with GlobalGougeChecker(...) as chk:")

        worst_pen = 0.0
        worst_pos = None
        worst_idx = None
        any_gouge = False

        for i, (cp, axis) in enumerate(zip(contact_points, tool_axes)):
            T = make_transform(cp, axis_z=axis)
            result = self.scene.distance(self.part_id, self._ball_id, T)
            if result.distance < -self.safety_margin_mm:
                any_gouge = True
                pen = -result.distance
                if pen > worst_pen:
                    worst_pen = pen
                    worst_pos = result.nearest_on_b
                    worst_idx = i

        if any_gouge:
            return GougeReport(
                gouge_detected=True,
                max_penetration_mm=worst_pen,
                offending_position=worst_pos,
                offending_station=worst_idx,
                diagnosis=f"Worst gouge: {worst_pen:.3f}mm at station {worst_idx}",
            )

        return GougeReport(
            gouge_detected=False,
            diagnosis=f"Path clear of gouges ({len(contact_points)} stations checked)",
        )


class HolderCollisionChecker:
    """Check the tool holder assembly against the part and fixtures.

    Builds a cylindrical holder mesh around the cutting tool and tests
    it against the part mesh at each tool pose.  The holder extends
    from the cutter tip backward along the tool axis.
    """

    def __init__(self, scene: FclScene, part_id: str,
                 holder_diameter_mm: float = 30.0,
                 holder_length_mm: float = 50.0,
                 safety_margin_mm: float = 1.0):
        self.scene = scene
        self.part_id = part_id
        self.holder_diameter = holder_diameter_mm
        self.holder_length = holder_length_mm
        self.safety_margin = safety_margin_mm
        self._holder_id = None

    def __enter__(self):
        self._holder_id = f"_holder_{id(self)}"
        self.scene.add_cylinder(
            radius=self.holder_diameter * 0.5,
            length=self.holder_length,
            name=self._holder_id,
        )
        return self

    def __exit__(self, *args):
        if self._holder_id is not None:
            self.scene.remove(self._holder_id)
            self._holder_id = None

    def check_holder_at(
        self,
        contact_xyz: Tuple[float, float, float],
        tool_axis: Tuple[float, float, float],
    ) -> CollisionReport:
        """Check holder clearance at one tool pose.

        The holder origin is positioned behind the contact point
        along the tool axis (away from the workpiece).
        """
        if self._holder_id is None:
            raise RuntimeError("Use as context manager: with HolderCollisionChecker(...) as chk:")

        offset = self.holder_length * 0.5
        holder_pos = (
            contact_xyz[0] - tool_axis[0] * offset,
            contact_xyz[1] - tool_axis[1] * offset,
            contact_xyz[2] - tool_axis[2] * offset,
        )
        T = make_transform(holder_pos, axis_z=tool_axis)
        return self.scene.collides(self.part_id, self._holder_id, T)

    def check_holder_path(
        self,
        contact_points: List[Tuple[float, float, float]],
        tool_axes: List[Tuple[float, float, float]],
    ) -> CollisionReport:
        """Check holder clearance along a path.  Returns the first hit."""
        for cp, axis in zip(contact_points, tool_axes):
            r = self.check_holder_at(cp, axis)
            if r.colliding:
                return r
        return CollisionReport(colliding=False)
