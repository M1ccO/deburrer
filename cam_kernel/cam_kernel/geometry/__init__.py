"""Geometry layer — OCCT-backed B-Rep and STEP handling.

This layer owns the CAD geometry pipeline: loading STEP files, building
topology graphs, extracting deburr features, and caching tessellations.

The primary backend is Open CASCADE Technology (OCCT) accessed through OCP
(cadquery-ocp).  A FreeCAD adapter can coexist as an alternative front-end
that bridges FreeCAD selections into the kernel's geometry types.
"""
