"""FCL collision scene.

Wraps the Flexible Collision Library (FCL) to provide deterministic
proximity and distance queries on geometric models.

Two levels of checking:

1. **Primitive shapes** — Box, Cylinder, Sphere, Cone for fast queries
2. **Triangle meshes** — BVHModel for arbitrary triangulated geometry

The scene holds multiple collision objects and supports:
- Pairwise distance queries
- Pairwise collision tests
- Continuous collision detection (CCD) for sweeping bodies

For the CAM kernel, this layer is used for:
- Holder vs. part collision checks
- Holder vs. fixture collision checks
- Holder vs. machine envelope checks
- Tool vs. workpiece gouge detection

Usage::

    scene = FclScene()
    part_id = scene.add_mesh(vertices, triangles, name="part")
    holder_id = scene.add_cylinder(radius=15, length=50, name="holder")
    holder_pose = transform_from_xyz_axis(...)

    distance = scene.distance(part_id, holder_id, holder_pose)
    colliding = scene.collides(part_id, holder_id, holder_pose)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np


class ObjectKind(str, Enum):
    PRIMITIVE = "primitive"
    MESH = "mesh"


@dataclass
class CollisionObject:
    id: str
    name: str
    kind: ObjectKind
    fcl_object: object
    is_static: bool = False


@dataclass
class DistanceResult:
    distance: float
    nearest_on_a: Optional[Tuple[float, float, float]] = None
    nearest_on_b: Optional[Tuple[float, float, float]] = None


@dataclass
class CollisionReport:
    colliding: bool
    contact_count: int = 0
    penetration_depth: float = 0.0
    normal: Optional[Tuple[float, float, float]] = None


def fcl_available() -> bool:
    try:
        import fcl
        return True
    except ImportError:
        return False


class FclScene:
    """Manages a collection of FCL collision objects."""

    def __init__(self):
        import fcl
        self._fcl = fcl
        self._objects: Dict[str, CollisionObject] = {}
        self._managers: Dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._objects)

    def add_box(self, sx: float, sy: float, sz: float, name: str = "",
                is_static: bool = False) -> str:
        """Add a box primitive. Returns the object ID."""
        obj = self._fcl.Box(sx, sy, sz)
        return self._add_primitive(obj, name, is_static)

    def add_sphere(self, radius: float, name: str = "",
                   is_static: bool = False) -> str:
        """Add a sphere primitive."""
        obj = self._fcl.Sphere(radius)
        return self._add_primitive(obj, name, is_static)

    def add_cylinder(self, radius: float, length: float, name: str = "",
                     is_static: bool = False) -> str:
        """Add a cylinder along Z axis."""
        obj = self._fcl.Cylinder(radius, length)
        return self._add_primitive(obj, name, is_static)

    def add_cone(self, radius: float, height: float, name: str = "",
                 is_static: bool = False) -> str:
        """Add a cone along Z axis."""
        obj = self._fcl.Cone(radius, height)
        return self._add_primitive(obj, name, is_static)

    def add_capsule(self, radius: float, length: float, name: str = "",
                    is_static: bool = False) -> str:
        """Add a capsule along Z axis."""
        obj = self._fcl.Capsule(radius, length)
        return self._add_primitive(obj, name, is_static)

    def add_mesh(self, vertices: List[Tuple[float, float, float]],
                 triangles: List[Tuple[int, int, int]],
                 name: str = "", is_static: bool = True) -> str:
        """Add a triangle mesh. Vertices as flat list of 3-floats per vertex."""
        bvh = self._fcl.BVHModel()
        bvh.beginModel(0, 0)
        for v in vertices:
            bvh.addVertex(np.array([v[0], v[1], v[2]], dtype=np.float64))
        for tri in triangles:
            bvh.addTriangle(tri[0], tri[1], tri[2])
        bvh.endModel()
        return self._add(bvh, name, ObjectKind.MESH, is_static)

    def add_stl(self, stl_path: str, name: str = "", is_static: bool = True) -> str:
        """Add geometry from a binary STL file."""
        import struct

        with open(stl_path, "rb") as f:
            f.read(80)
            count = struct.unpack("<I", f.read(4))[0]
            vertices_set = {}
            vertices = []
            triangles = []

            for _ in range(count):
                f.read(12)
                pts = []
                for _ in range(3):
                    x, y, z = struct.unpack("<fff", f.read(12))
                    key = (round(x, 6), round(y, 6), round(z, 6))
                    if key not in vertices_set:
                        vertices_set[key] = len(vertices)
                        vertices.append(key)
                    pts.append(vertices_set[key])
                triangles.append(tuple(pts))
                f.read(2)

        flat_verts = [c for v in vertices for c in v]
        return self.add_mesh(flat_verts, triangles, name=name, is_static=is_static)

    def _add_primitive(self, primitive, name: str, is_static: bool) -> str:
        return self._add(primitive, name, ObjectKind.PRIMITIVE, is_static)

    def _add(self, geometry, name: str, kind: ObjectKind, is_static: bool) -> str:
        obj = self._fcl.CollisionObject(geometry)
        cid = name if name else f"obj_{len(self._objects)}"
        self._objects[cid] = CollisionObject(
            id=cid, name=name, kind=kind, fcl_object=obj, is_static=is_static,
        )
        return cid

    def set_transform(self, obj_id: str, transform) -> None:
        """Set the world-space transform of an object.

        Accepts either a 4x4 numpy array or an fcl.Transform.
        """
        if obj_id not in self._objects:
            raise KeyError(f"Object {obj_id} not in scene")
        fcl_tf = self._to_fcl_transform(transform)
        self._objects[obj_id].fcl_object.setTransform(fcl_tf)

    def get_transform(self, obj_id: str) -> np.ndarray:
        """Get the current transform of an object as a 4x4 numpy array."""
        if obj_id not in self._objects:
            raise KeyError(f"Object {obj_id} not in scene")
        fcl_tf = self._objects[obj_id].fcl_object.getTransform()
        return self._to_numpy_transform(fcl_tf)

    def _to_fcl_transform(self, transform):
        """Convert numpy array (4x4) to fcl.Transform."""
        if isinstance(transform, np.ndarray):
            fcl_tf = self._fcl.Transform()
            if transform.shape == (4, 4):
                fcl_tf.setRotation(transform[0:3, 0:3])
                fcl_tf.setTranslation(transform[0:3, 3])
            else:
                fcl_tf.setTranslation(np.asarray(transform).flatten()[:3])
            return fcl_tf
        return transform

    def _to_numpy_transform(self, fcl_tf) -> np.ndarray:
        """Convert fcl.Transform to 4x4 numpy array."""
        T = np.eye(4)
        T[0:3, 0:3] = fcl_tf.getRotation()
        T[0:3, 3] = fcl_tf.getTranslation()
        return T

    def distance(self, a_id: str, b_id: str,
                 transform_b=None) -> DistanceResult:
        """Compute the minimum distance between two objects.

        If ``transform_b`` is given, object b is temporarily set to that
        transform (then restored).  Object a stays at its stored transform.
        """
        if a_id not in self._objects or b_id not in self._objects:
            raise KeyError("Object not in scene")

        a = self._objects[a_id].fcl_object
        b = self._objects[b_id].fcl_object

        if transform_b is not None:
            fcl_tf = self._to_fcl_transform(transform_b)
            old_tf = b.getTransform()
            b.setTransform(fcl_tf)
            try:
                return self._do_distance(a, b)
            finally:
                b.setTransform(old_tf)
        return self._do_distance(a, b)

    def _do_distance(self, a, b) -> DistanceResult:
        req = self._fcl.DistanceRequest()
        res = self._fcl.DistanceResult()
        dist = self._fcl.distance(a, b, req, res)
        nearest_a = None
        nearest_b = None
        if res.nearest_points is not None and len(res.nearest_points) >= 2:
            nearest_a = tuple(float(x) for x in res.nearest_points[0])
            nearest_b = tuple(float(x) for x in res.nearest_points[1])
        return DistanceResult(
            distance=float(dist),
            nearest_on_a=nearest_a,
            nearest_on_b=nearest_b,
        )

    def collides(self, a_id: str, b_id: str,
                 transform_b=None,
                 max_contacts: int = 10) -> CollisionReport:
        """Test whether two objects collide.

        If ``transform_b`` is given, object b is temporarily positioned.
        """
        if a_id not in self._objects or b_id not in self._objects:
            raise KeyError("Object not in scene")

        a = self._objects[a_id].fcl_object
        b = self._objects[b_id].fcl_object

        if transform_b is not None:
            fcl_tf = self._to_fcl_transform(transform_b)
            old_tf = b.getTransform()
            b.setTransform(fcl_tf)
            try:
                return self._do_collide(a, b, max_contacts)
            finally:
                b.setTransform(old_tf)
        return self._do_collide(a, b, max_contacts)

    def _do_collide(self, a, b, max_contacts: int) -> CollisionReport:
        req = self._fcl.CollisionRequest()
        req.num_max_contacts = max_contacts
        req.enable_contact = True
        res = self._fcl.CollisionResult()
        num_contacts = self._fcl.collide(a, b, req, res)
        colliding = (num_contacts > 0)
        contact_list = list(res.contacts) if hasattr(res, "contacts") else []
        normal = None
        penetration = 0.0
        if len(contact_list) > 0:
            contact = contact_list[0]
            if contact.o1 == a:
                normal = (-contact.normal[0], -contact.normal[1], -contact.normal[2])
            else:
                normal = tuple(contact.normal)
            penetration = float(contact.penetration_depth)
        return CollisionReport(
            colliding=colliding,
            contact_count=len(contact_list),
            penetration_depth=penetration,
            normal=normal,
        )

    def distance_to_all(self, a_id: str,
                        transform_a: Optional[np.ndarray] = None,
                        skip_static: bool = True) -> Dict[str, DistanceResult]:
        """Compute distance from object a to all other objects.

        Returns a dict mapping obj_id -> DistanceResult.
        """
        results = {}
        for other_id, other in self._objects.items():
            if other_id == a_id:
                continue
            if skip_static and other.is_static:
                continue
            results[other_id] = self.distance(a_id, other_id, transform_a)
        return results

    def closest_object(self, a_id: str,
                       transform_a: Optional[np.ndarray] = None,
                       skip_static: bool = True) -> Optional[Tuple[str, DistanceResult]]:
        """Return the closest non-static object to a."""
        distances = self.distance_to_all(a_id, transform_a, skip_static)
        if not distances:
            return None
        return min(distances.items(), key=lambda kv: kv[1].distance)

    def remove(self, obj_id: str) -> None:
        """Remove an object from the scene."""
        self._objects.pop(obj_id, None)

    def clear(self) -> None:
        """Remove all objects."""
        self._objects.clear()
        self._managers.clear()


def make_transform(xyz: Tuple[float, float, float],
                   axis_z: Tuple[float, float, float] = (0.0, 0.0, 1.0),
                   axis_x: Optional[Tuple[float, float, float]] = None) -> np.ndarray:
    """Build a 4x4 transform from position and tool axis.

    The Z axis of the local frame is the tool direction.  The X axis is
    either given or computed as the closest perpendicular to the world X.

    Args:
        xyz: Position of the local frame origin.
        axis_z: Tool axis (forward direction).
        axis_x: Optional preferred X direction (otherwise picked automatically).

    Returns:
        4x4 numpy array (homogeneous transform).
    """
    z = np.array(axis_z, dtype=np.float64)
    z_norm = np.linalg.norm(z)
    if z_norm < 1e-12:
        z = np.array([0.0, 0.0, 1.0])
    else:
        z = z / z_norm

    if axis_x is not None:
        x = np.array(axis_x, dtype=np.float64)
        x = x - z * np.dot(x, z)
        x_norm = np.linalg.norm(x)
        if x_norm < 1e-6:
            x = _perpendicular(z)
        else:
            x = x / x_norm
    else:
        x = _perpendicular(z)

    y = np.cross(z, x)
    y_norm = np.linalg.norm(y)
    if y_norm > 1e-12:
        y = y / y_norm

    T = np.eye(4)
    T[0:3, 0] = x
    T[0:3, 1] = y
    T[0:3, 2] = z
    T[0:3, 3] = xyz
    return T


def _perpendicular(v: np.ndarray) -> np.ndarray:
    """Return a unit vector perpendicular to v."""
    if abs(v[0]) < 0.9:
        perp = np.array([1.0, 0.0, 0.0])
    else:
        perp = np.array([0.0, 1.0, 0.0])
    perp = perp - v * np.dot(perp, v)
    return perp / np.linalg.norm(perp)
