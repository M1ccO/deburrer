"""Unit tests for the FCL collision scene and gouge checks.

These tests require python-fcl to be installed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam_kernel.collision.fcl_scene import FclScene, make_transform
from cam_kernel.collision.gouge_checks import (
    GougeReport,
    HolderCollisionChecker,
    LocalGougeChecker,
    fcl_available,
)


pytestmark = pytest.mark.skipif(
    not fcl_available(), reason="python-fcl not installed"
)


class TestFclScene:
    def test_scene_creation(self):
        scene = FclScene()
        assert len(scene) == 0

    def test_add_box(self):
        scene = FclScene()
        box_id = scene.add_box(10, 10, 10, name="box")
        assert len(scene) == 1
        assert box_id in scene._objects

    def test_distance_separated(self):
        scene = FclScene()
        scene.add_box(10, 10, 10)
        ball_id = scene.add_sphere(2.0)
        T = make_transform((10, 0, 0))
        r = scene.distance(ball_id, scene._objects[next(iter(scene._objects))].id, T)
        assert r.distance == pytest.approx(3.0, abs=0.01)

    def test_distance_far(self):
        scene = FclScene()
        box_id = scene.add_box(10, 10, 10)
        ball_id = scene.add_sphere(2.0)
        T = make_transform((100, 0, 0))
        r = scene.distance(ball_id, box_id, T)
        assert r.distance == pytest.approx(93.0, abs=0.01)

    def test_collide_overlap(self):
        scene = FclScene()
        box_id = scene.add_box(10, 10, 10)
        ball_id = scene.add_sphere(2.0)
        T = make_transform((3, 0, 0))
        r = scene.collides(ball_id, box_id, T)
        assert r.colliding
        assert r.penetration_depth > 0

    def test_collide_separated(self):
        scene = FclScene()
        box_id = scene.add_box(10, 10, 10)
        ball_id = scene.add_sphere(2.0)
        T = make_transform((20, 0, 0))
        r = scene.collides(ball_id, box_id, T)
        assert not r.colliding

    def test_cylinder_collision(self):
        scene = FclScene()
        cyl_id = scene.add_cylinder(5, 10)
        box_id = scene.add_box(20, 20, 20)
        T = make_transform((10, 0, 0))
        r = scene.collides(cyl_id, box_id, T)
        assert r.colliding

    def test_make_transform_axis(self):
        T = make_transform((1, 2, 3), axis_z=(0, 0, 1))
        assert T.shape == (4, 4)
        assert T[0, 3] == 1
        assert T[1, 3] == 2
        assert T[2, 3] == 3
        assert np.allclose(T[0:3, 2], [0, 0, 1])

    def test_make_transform_custom_axis(self):
        T = make_transform((0, 0, 0), axis_z=(1, 0, 0), axis_x=(0, 0, 1))
        assert np.allclose(T[0:3, 2], [1, 0, 0])

    def test_remove_object(self):
        scene = FclScene()
        box_id = scene.add_box(10, 10, 10)
        assert len(scene) == 1
        scene.remove(box_id)
        assert len(scene) == 0

    def test_clear_scene(self):
        scene = FclScene()
        scene.add_box(1, 1, 1)
        scene.add_sphere(1)
        scene.add_cylinder(1, 1)
        assert len(scene) == 3
        scene.clear()
        assert len(scene) == 0


class TestGougeChecks:
    def _make_box_part(self) -> FclScene:
        scene = FclScene()
        part_id = scene.add_box(20, 20, 20)
        return scene, part_id

    def test_local_gouge_no_intrusion(self):
        scene, part_id = self._make_box_part()
        checker = LocalGougeChecker(scene, part_id)
        r = checker.check_at((20, 0, 0), (0, 0, 1), cutter_radius=3.0)
        assert not r.gouge_detected
        assert r.max_penetration_mm >= 0

    def test_local_gouge_clear(self):
        scene, part_id = self._make_box_part()
        checker = LocalGougeChecker(scene, part_id, safety_margin_mm=0.0)
        r = checker.check_at((20, 0, 0), (0, 0, 1), cutter_radius=3.0)
        assert not r.gouge_detected

    def test_local_gouge_intrusion(self):
        scene, part_id = self._make_box_part()
        checker = LocalGougeChecker(scene, part_id, safety_margin_mm=0.0)
        r = checker.check_at((8, 0, 0), (0, 0, 1), cutter_radius=3.0)
        assert r.gouge_detected
        assert r.max_penetration_mm > 0

    def test_global_gouge_clear_path(self):
        scene, part_id = self._make_box_part()
        contacts = [(20, 0, 0), (20, 5, 0), (20, 10, 0)]
        axes = [(0, 0, 1)] * 3
        with GlobalGougeChecker(scene, part_id, cutter_radius=3.0) as chk:
            r = chk.check_path(contacts, axes)
        assert not r.gouge_detected

    def test_global_gouge_with_intrusion(self):
        scene, part_id = self._make_box_part()
        contacts = [(20, 0, 0), (8, 0, 0), (20, 5, 0)]
        axes = [(0, 0, 1)] * 3
        with GlobalGougeChecker(scene, part_id, cutter_radius=3.0) as chk:
            r = chk.check_path(contacts, axes)
        assert r.gouge_detected
        assert r.offending_station == 1

    def test_holder_check_clear(self):
        scene, part_id = self._make_box_part()
        with HolderCollisionChecker(
            scene, part_id, holder_diameter_mm=10, holder_length_mm=20
        ) as chk:
            r = chk.check_holder_at((20, 0, 0), (0, 0, 1))
        assert not r.colliding

    def test_holder_check_collision(self):
        scene, part_id = self._make_box_part()
        with HolderCollisionChecker(
            scene, part_id, holder_diameter_mm=20, holder_length_mm=20
        ) as chk:
            r = chk.check_holder_at((15, 0, 0), (0, 0, 1))
        assert r.colliding


from cam_kernel.collision.gouge_checks import GlobalGougeChecker  # noqa: E402
