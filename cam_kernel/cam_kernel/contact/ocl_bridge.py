"""OpenCAMLib bridge.

Wraps OpenCAMLib's C++ library for cutter-projection algorithms:
- **drop_cutter** — project the cutter onto a triangulated surface
- **push_cutter** — push the cutter along a surface with fiber direction
- **waterline** — constant-Z contour following

OpenCAMLib works on triangle meshes, not B-Rep.  The tessellation cache
provides the mesh input.  This bridge translates between the kernel's
data types and OCL's C++ structures (via the Python bindings or a ctypes
FFI).

The bridge is optional — the kernel falls back to local contact solvers
when OCL is not installed.

TODO:
 - Python bindings or ctypes wrapper for OCL C++ API
 - Mesh upload from tessellation cache
 - Drop-cutter for roughing and rest-material detection
 - Push-cutter for surface finishing with fiber direction
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class OclSetup:
    cutter_radius: float
    cutter_length: float
    sampling: float = 0.5


def ocl_available() -> bool:
    """Check whether OpenCAMLib Python bindings are available."""
    try:
        import ocl
        return True
    except ImportError:
        return False


def drop_cutter(mesh, setup: OclSetup, points) -> list:
    """Run drop-cutter on a mesh.

    TODO: Implement OCL integration.
    """
    if not ocl_available():
        raise ImportError("OpenCAMLib (ocl) not installed")
    raise NotImplementedError("OCL bridge not yet implemented")


def push_cutter(mesh, setup: OclSetup, fibers) -> list:
    """Run push-cutter along fibers on a mesh.

    TODO: Implement OCL integration.
    """
    if not ocl_available():
        raise ImportError("OpenCAMLib (ocl) not installed")
    raise NotImplementedError("OCL bridge not yet implemented")
