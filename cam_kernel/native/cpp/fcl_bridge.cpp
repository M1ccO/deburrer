// FCL bridge — exposes FCL collision queries to Python via pybind11.
//
// Provides:
//   - create_scene(part_vertices, part_triangles, fixture_vertices, fixture_triangles)
//   - distance_query(scene, tool_vertices, tool_triangles, transform)
//   - collision_check(scene, tool_vertices, tool_triangles, transform)
//
// TODO: Implement pybind11 bindings for FCL BroadPhaseCollisionManager
//       and GJK/EPA distance queries.

#include <fcl/fcl.h>
#include <vector>
#include <array>

// Stub — real implementation requires fcl headers and pybind11
// See https://github.com/flexible-collision-library/fcl
