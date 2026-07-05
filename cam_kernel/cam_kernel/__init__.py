"""Standalone multiaxis CAM kernel for deburring and surface finishing.

This package provides a Python-first CAM kernel built around OCCT for B-Rep
geometry and STEP exchange.  The kernel is designed to be independent of any
particular CAD front-end (FreeCAD, Blender, etc.) so that those tools become
clients rather than the place where the kernel lives.

Core layers:

- ``api/``        — YAML/JSON job, tool, and machine schemas
- ``geometry/``   — OCCT session, STEP I/O, topology graph, feature extraction
- ``sampling/``   — Edge and face sampling, local frame construction
- ``tools/``      — Cutter models, holder models, engagement rules
- ``contact/``    — OpenCAMLib bridge, local contact solvers
- ``posture/``    — Axis seeding, posture cost, optimization
- ``kinematics/`` — Machine-specific IK (NTX2500), branch selection
- ``collision/``  — FCL scene management, gouge checks, envelope
- ``smoothing/``  — Pose filtering, joint-space filtering, feed planning
- ``post/``       — FANUC NTX post-processor, NC formatters
- ``viz/``        — Backplot, debug export

The ``native/`` tree contains optional Rust and C++ acceleration modules
that can be compiled for performance-critical operations.

Usage::

    from cam_kernel.geometry import OcctSession, StepIO
    from cam_kernel.tools import CutterLibrary
    from cam_kernel.contact import ContactSolver
    from cam_kernel.kinematics import Ntx2500Kinematics
    from cam_kernel.collision import CollisionChecker
    from cam_kernel.post import FanucNtxPost
"""

__version__ = "0.1.0"
