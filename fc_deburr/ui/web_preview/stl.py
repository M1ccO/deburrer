import struct
from typing import List, Tuple

from ...domain.models import Vec3

Triangle = Tuple[Vec3, Vec3, Vec3]


def read_binary_stl(path: str) -> Tuple[List[Triangle], List[Vec3]]:
    with open(path, "rb") as stream:
        stream.read(80)
        count = struct.unpack("<I", stream.read(4))[0]
        triangles = []
        normals = []
        for _ in range(count):
            normal = struct.unpack("<fff", stream.read(12))
            points = [
                struct.unpack("<fff", stream.read(12))
                for _ in range(3)
            ]
            triangles.append((points[0], points[1], points[2]))
            normals.append(normal)
            stream.read(2)
        return triangles, normals
