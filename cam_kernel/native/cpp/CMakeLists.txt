cmake_minimum_required(VERSION 3.16)
project(cam_kernel_native_cpp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optional dependencies — build what is available
find_package(Python3 COMPONENTS Interpreter Development QUIET)
find_package(Eigen3 QUIET)

# FCL bridge
option(BUILD_FCL_BRIDGE "Build FCL collision bridge" OFF)
if(BUILD_FCL_BRIDGE)
    find_package(fcl REQUIRED)
    add_library(fcl_bridge SHARED fcl_bridge.cpp)
    target_link_libraries(fcl_bridge PRIVATE fcl::fcl)
    if(Eigen3_FOUND)
        target_link_libraries(fcl_bridge PRIVATE Eigen3::Eigen)
    endif()
endif()

# OCCT bridge
option(BUILD_OCCT_BRIDGE "Build OCCT geometry bridge" OFF)
if(BUILD_OCCT_BRIDGE)
    find_package(OpenCASCADE REQUIRED)
    add_library(occt_bridge SHARED occt_bridge.cpp)
    target_include_directories(occt_bridge PRIVATE ${OpenCASCADE_INCLUDE_DIR})
    target_link_libraries(occt_bridge PRIVATE ${OpenCASCADE_LIBRARIES})
endif()

# OCL bridge
option(BUILD_OCL_BRIDGE "Build OpenCAMLib bridge" OFF)
if(BUILD_OCL_BRIDGE)
    add_library(ocl_bridge SHARED ocl_bridge.cpp)
    target_link_libraries(ocl_bridge PRIVATE ocl)
endif()
