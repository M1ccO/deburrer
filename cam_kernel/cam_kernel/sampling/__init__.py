"""Sampling layer — discretised points on edges and faces.

Converts continuous CAD geometry into ordered arrays of sample points,
each carrying position, tangent, and face normals.  These samples are
the input to the analytic contact solvers.

Samplers are responsible for:
- Parameter spacing (constant arc-length or chordal)
- Corner detection (tangent discontinuity at vertex junctions)
- C0 anchoring (identifying the start vertex)
- Sharp-discontinuity blocking (invalid for simultaneous modes)

All samplers return plain tuples of immutable dataclass values with no
FreeCAD or OCCT handles — they are pure geometry, safe to pass anywhere
in the kernel.
"""
