// OCCT bridge — exposes OCCT B-Rep operations to Python via pybind11.
//
// Provides:
//   - read_step(path) -> TopoDS_Shape
//   - extract_edges(shape) -> [TopoDS_Edge]
//   - extract_faces(shape) -> [TopoDS_Face]
//   - edge_normals(edge, param) -> (guide_normal, other_normal)
//   - tessellate(shape, tolerance) -> (vertices, triangles)
//
// TODO: Implement pybind11 bindings for OCCT topology and geometry.

#include <TopoDS_Shape.hxx>
#include <TopExp_Explorer.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <STEPControl_Reader.hxx>

// Stub — real implementation requires OpenCASCADE headers and pybind11
// See https://dev.opencascade.org/
