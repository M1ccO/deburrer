"""CAM kernel native modules — Rust and C++ performance acceleration.

Each subdirectory contains a standalone build system:

- ``rust/`` — Cargo workspace with pyo3-based Python extension modules
  for fast vector math and posture cost computation.
- ``cpp/`` — CMake project with pybind11-based bridges to OCCT, FCL,
  and OpenCAMLib.

Build the Rust extension::

    cd native/rust && cargo build --release

Build the C++ bridges (optional, requires OCCT/FCL/OCL)::

    cd native/cpp && mkdir build && cd build && cmake .. && cmake --build .
"""
