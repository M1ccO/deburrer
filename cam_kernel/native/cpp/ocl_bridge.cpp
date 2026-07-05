// OCL bridge — exposes OpenCAMLib cutter projection to Python via pybind11.
//
// Provides:
//   - drop_cutter(points, mesh, cutter) -> [ToolPosition]
//   - push_cutter(fibers, mesh, cutter) -> [ToolPosition]
//   - waterline(mesh, cutter, z_values) -> [Fiber]
//
// TODO: Implement pybind11 bindings for ocl::DropCutter,
//       ocl::PushCutter, and ocl::Waterline.

// Stub — real implementation requires ocl headers and pybind11
// See https://github.com/aewallin/opencamlib
