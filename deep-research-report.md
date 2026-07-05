# Logical Technology Choice for Building an Open Deburring and Multiaxis CAM Kernel

## What your kernel actually has to solve

For the kind of system you described, the hard part is not G-code formatting or smooth servo motion. The hard part is building a kernel that can start from real CAD geometry, understand **edges, adjacent faces, normals, tangents, offsets, and cutter shape**, then compute a valid **tool-contact condition**, a valid **tool-axis field**, and finally a machine-realizable posture for indexed 3+2, 4+1, and full simultaneous 5-axis motion. Open CASCADE Technology is specifically built around B-Rep topology and geometry, including curves, surfaces, NURBS, and STEP exchange, while LinuxCNC’s kinematics model makes the same separation explicit: Cartesian programming on one side, machine-joint kinematics on the other. OpenCAMLib, by contrast, is strongest on cutter-projection algorithms such as drop-cutter and push-cutter, not on full B-Rep semantics. citeturn11search12turn1search0turn5search3turn3search0

That distinction matters for deburring more than it first appears. Edge deburring and face-following are usually **B-Rep-first** problems, because you need to know which faces meet at an edge, what the local normals are, how the tool should lean away from an adjacent wall, and whether a ball, chamfer, or corner-radius cutter is supposed to touch with its tip, flank, or some controlled latitude on the sphere. A mesh-only system can often simulate or approximate that, but it has to reconstruct semantics that a STEP/B-Rep model already contains. That is why a logical kernel for your goal should treat **geometry/contact/posture** as the main engine, with posting and simulation downstream. citeturn1search0turn11search12turn3search0turn8search0

The encouraging part is that the same core can serve all the later expansion steps you mentioned. Indexed 3+2 and 4+1 are not separate universes; they are simpler cases of the same architecture, where the tool axis is held constant over a region or stepped between regions instead of varying continuously. Even OpenMill’s own strategy list presents indexed 3+2, indexed 4+1, and simultaneous 5-axis as different modes within one broader multiaxis framework, and LinuxCNC’s kinematics documentation reflects the same layered view of Cartesian intent versus machine-axis realization. citeturn13view0turn5search19turn5search3

## How the listed libraries fit the problem

### The Rust stack is promising, but not yet a complete kernel foundation

OpenMill is technically ambitious and already claims indexed and simultaneous multiaxis strategies, Fanuc-style TCPM output, tool libraries, verification, and simulation. But in its present form it is still clearly **experimental**, very small, and most importantly **mesh-first**: its README describes feature extraction from mesh geometry, collision against part meshes, and importing STL or 3MF models rather than STEP/B-Rep solids. That makes it interesting as a study project and a future collaboration target, but it is not yet the most logical base for an **edge/face-driven deburring kernel** that depends on robust CAD topology. citeturn13view0turn16view1turn16view2

The Rust supporting crates on your list are useful, but each solves only a slice of the problem. `nalgebra` is a broad linear algebra package with matrices, transforms, decompositions, and geometric operations; `glam` is a lighter, faster, graphics-oriented math layer; `lyon` is mainly a 2D path and tessellation library for turning vector paths into triangles; and the Rust `gcode` crate is a parser/emitter layer with a zero-allocation parsing core. Those are all valuable pieces for math, UI, preview, and NC parsing, but none of them gives you STEP reading, B-Rep topology, surface normals from analytic faces, or 5-axis cutter-contact logic. In practice, they are enabling tools around the kernel, not the kernel itself. citeturn0search1turn0search2turn0search19turn9search0

If you eventually choose Rust as your long-term systems language, `nalgebra` is the better fit for CAM math than `glam`, because CAM kernels care about transforms, coordinate frames, and general linear algebra more than game-style convenience vectors. `glam` still makes sense for viewers, GPU-facing tools, and fast rendering-adjacent code. `lyon` is better thought of as a UI/path-processing helper than a manufacturing-grade offset engine, and the `gcode` crate is worth using for post verification or program rewriting, not for posture computation itself. That conclusion follows directly from the stated scope of those crates. citeturn0search1turn0search2turn0search19turn9search0

### The geometry layer is where the real choice is made

Among the geometry kernels, **OCCT is the strongest match by a wide margin**. It is explicitly positioned as a C++ class library for CAD/CAM/CAE applications, it models geometry and topology separately in B-Rep form, and it handles STEP exchange. Its license is also comparatively practical for open development and even many commercial situations, using LGPL 2.1 with the OCCT exception. For a deburring-first kernel that must understand imported solids as real manufacturing geometry, this is the most important asset on the entire list. citeturn11search12turn1search0turn14search0turn14search4

CGAL is powerful, especially for polygon mesh processing, AABB trees, closest-point queries, and computational geometry on triangulated shapes. But it is a more conditional choice. First, its sweet spot is not full industrial CAD B-Rep in the OCCT sense; second, its licensing is more complicated because CGAL is dual-licensed under open-source GPL/LGPL terms and commercial licenses, with per-package differences. That makes it very useful as a **specialized add-on** for meshing, offsets, or difficult geometry problems, but a less comfortable primary foundation for your kernel. citeturn1search1turn1search9turn14search1turn14search21

`libigl` is also narrower than OCCT. It is a simple geometry-processing library centered on triangle meshes and discrete geometry operators, and it is primarily MPL 2.0 licensed. That makes it attractive for mesh repair, remeshing, and geometric experimentation, but it does not replace a full CAD kernel for STEP solids and topological face-edge reasoning. `OpenCSG`, meanwhile, is not a CAM kernel at all; it is an OpenGL image-based CSG rendering library, and its visible release history is old. It can help visualize constructive solids, but it does not solve cutter contact, gouge tests, or multiaxis posture planning. citeturn1search2turn15search4turn1search3turn1search15

### The 2D engines are useful, but only in specific parts of the stack

`Clipper2` is one of the easiest recommendations on your list. It is robust, fast, focused on polygon clipping and offsetting, and uses the permissive Boost Software License. That makes it an excellent component for 2D pocket boundaries, profile offsets, containment tests, and support logic for section-based planning. If your kernel later grows into pocketing, rest machining, silhouette operations, and boundary processing, Clipper2 will almost certainly earn its place. citeturn2search0turn2search8turn14search2

`OpenVoronoi` is more niche. Its purpose is very specific: computing 2D Voronoi diagrams for point, segment, and eventually arc sites. That can absolutely matter for some high-speed 2D path generation ideas, but it is not central to an edge/face deburring kernel, and the project’s own description still frames arc support as a work in progress. It is a “later, if needed” tool rather than a day-one dependency. citeturn2search1turn2search17

`libslic3r` and `CuraEngine` are strong engineering projects, but they are strong in the wrong domain. Both are slicer engines for 3D printing and generate printer toolpaths from model geometry; `libslic3r` can be used as a standalone slicing core, and CuraEngine is explicitly a fast backend for turning 3D models into printer G-code. You can learn from them about path ordering, slicing pipelines, and geometric partitioning, but they are not a logical foundation for subtractive multiaxis milling. citeturn2search22turn2search14turn2search3

### The existing CAM engines are best used as references, not as your core

OpenCAMLib is the most directly relevant CAM library on the list. It is a C++ library with Python and JavaScript access, and its documented strengths are cutter-location algorithms like **drop-cutter** and **push-cutter**. That makes it extremely valuable for 3D surface toolpaths, waterline-like ideas, and understanding cutter projection. It is also now LGPL-licensed, which makes integration easier than its original GPL history. But OpenCAMLib is still fundamentally a toolpath-algorithm library, not a full multiaxis CAD-aware deburring kernel. It is a very strong **component**, not the whole foundation. citeturn3search0turn3search12turn10search0turn10search12

`LibArea` is useful but narrow: it exists for profile and pocket operations and has historically been reused in HeeksCNC and FreeCAD’s CAM/Path work. That makes it relevant for classic 2D/2.5D operations, but not a serious answer to simultaneous 5-axis posture. `PyCAM` is similarly constrained; it openly describes itself as a toolpath generator for **3-axis** CNC machining. `Kiri:Moto` is genuinely interesting and actively developed, but it is a browser-based CNC/laser/printing toolpath generator aimed at accessibility and web delivery, not at an industrial-grade B-Rep-first multiaxis kernel. citeturn3search9turn3search13turn3search15turn3search23turn3search2turn3search10

`BlenderCAM`, now also documented as FabexCNC, is actively developed and can generate CNC toolpaths and G-code inside Blender, with OpenCAMLib among its dependencies. It is worth studying for workflow ideas, user interaction, and some path-generation patterns. FreeCAD CAM/Path is similarly worth studying, especially because it already combines CAD context with CAM jobs and uses OpenCAMLib for some 3D surface work; however, FreeCAD’s own current discussions show that multiaxis support is still a work in progress, and even simulation of rotated axes is an active issue. That means both are valuable **reference codebases** and possible front ends, but not the cleanest place to bury your kernel. citeturn4search7turn4search11turn4search4turn8search5turn8search1turn8search0turn8search20

The CNC Toolkit is historically important because it explicitly targeted 3-, 4-, and 5-axis work and advertised full 5-axis contouring toolpaths. But it is also a legacy script/plugin ecosystem tied to 3ds Max/Gmax-era tooling and is best treated as inspiration or archaeology rather than as a modern base. citeturn4search6turn4search17turn4search9

## The strongest practical foundation for your kernel

The most logical architecture for your goal is a **Python-first hybrid stack centered on OCCT**, not a pure-Rust or pure-FreeCAD approach. The reason is straightforward: Python gives you very fast development, easy experimentation, and access to mature Python bindings for OCCT, while OCCT gives you the B-Rep and STEP geometry that an edge/face-first deburring kernel needs. Useful modern OCCT bindings already exist: `pythonOCC` is mature, `OCP` provides thin bindings used by CadQuery, and `pyOCCT` explicitly frames itself as a route to rapid CAD/CAM application development in Python. citeturn11search0turn11search1turn11search2turn11search6

A logical core stack therefore looks like this: **OCCT bindings for geometry and STEP**, **Clipper2** for 2D boundary and offset work, **OpenCAMLib** where cutter projection or surface-path ideas are useful, **custom contact and posture solvers** for ball/chamfer/bull tools, **custom NTX-style machine kinematics** inspired by LinuxCNC’s kinematics separation, and **FCL or PyBullet** for collision/proximity checks. This stack is favorable not only technically but also legally: OCCT’s LGPL-plus-exception, OpenCAMLib’s LGPL, Clipper2’s Boost license, and FCL’s BSD license are all relatively workable for an open kernel. citeturn14search0turn14search4turn10search0turn14search2turn14search3

For collision checking, FCL is the stronger “engine-room” option if you want deterministic proximity and distance queries on geometric models, while PyBullet is the lower-friction prototyping option because it exposes collision and closest-point functionality directly through Python. That is an engineering judgment, but it follows the way the two projects position themselves: FCL is a proximity-query library; PyBullet is a broader robotics simulation environment with collision APIs. citeturn6search6turn6search2turn7search0turn7search2

For machine kinematics, LinuxCNC is worth studying even if your target controller is Fanuc. Its documentation is unusually explicit about forward and inverse kinematics, custom kinematics modules, and 5-axis kinematic examples. That makes it an excellent **reference model** for how to separate world-space toolpath intent from machine-joint realization. For an NTX-style machine, though, I would still recommend writing your own dedicated kinematic solver rather than trying to bolt a generic robotics planner directly into the runtime. citeturn5search3turn5search15turn5search19

## What to use only as references or later-stage additions

Pinocchio and Pybotics are both genuinely useful, but they are not mandatory on day one. Pinocchio is a fast C++/Python rigid-body dynamics and kinematics library with forward and inverse kinematics; Pybotics is a simpler Python toolbox for robot kinematics and calibration. For a machine tool with known axis arrangement, a direct custom solver will usually be easier and more transparent than a general robotics stack. Still, both are excellent for validation, calibration experiments, and building an analysis harness around your machine model. citeturn5search0turn5search4turn15search5turn5search1turn5search9turn15search2

MoveIt 2 and Gazebo belong in the same “later, if you really need it” bucket. MoveIt 2 is a serious manipulation and motion-planning platform with collision checking and planner pipelines, and Gazebo is a full robotics simulator. If you someday want a digital twin, joint-limit-aware collision scenes, and broader robotic-style planning experiments, they are excellent tools. But for a CAM kernel whose first job is contact geometry and tool posture, they are much heavier than necessary. That is an inference, but it is supported by the fact that these frameworks are explicitly aimed at full robot motion planning and simulation ecosystems. citeturn6search0turn6search4turn15search19turn6search3turn6search7

`industrial_core` and the old `kuka_experimental`/ROS-Industrial lineage are even less central here. ROS-Industrial itself notes that `industrial_core` is a ROS 1-era component and is no longer needed in ROS 2 in the way it once was. That makes it a weak choice for a new CAM kernel effort. OpenRAVE is also best classified as legacy-adjacent today: still important historically, still usable, but often installed from source and associated with older build and compatibility assumptions. citeturn5search10turn5search2turn12search0turn12search1turn12search8

CGAL and `libigl` sit in a middle position. They are not wrong choices; they are just not the first choice for your specific problem. If later you need advanced mesh repair, geodesic computations, remeshing, or specialized computational geometry beyond what OCCT and OpenCAMLib give you, either can become very valuable. For the first kernel, though, bringing them in too early would probably increase integration work faster than it increases useful capability. citeturn1search1turn1search2turn15search4turn14search21

## Python first versus Rust first

If the question is what is **most logical now**, the answer is **Python first**. Python lets you compose OCCT bindings, collision libraries, and numeric code quickly, and some of the OCCT Python projects explicitly pitch themselves as rapid CAD/CAM development tools. That directly matches your situation, because your biggest unknowns are still geometric and kinematic, not low-level performance. citeturn11search0turn11search6turn11search9

A Rust-first approach only becomes the logical winner if you are deliberately choosing a longer path in exchange for long-term systems control. Rust has strong math crates, a decent G-code parser story, and projects like OpenMill show that people are pushing open CAM in that direction. But the list you provided also shows the gap very clearly: the Rust entries are mostly math, parsing, and experimental-project layers, while the mature CAD and CAM geometry layers are still dominated by C++ libraries such as OCCT, OpenCAMLib, CGAL, and FCL. So a pure-Rust kernel would either require a great deal of fresh geometry work or a foreign-function interface to precisely those C++ components anyway. citeturn13view0turn16view1turn0search1turn0search2turn9search0turn11search12turn3search0turn6search6

That leads to a practical compromise. If you want Rust in the story, the most sensible split is to keep **geometry-heavy kernel development in Python plus OCCT first**, then migrate hot loops or long-term subsystems later. Alternatively, use Rust for the outer layers—UI, simulation, post-processing, program verification, project storage—while the geometry core calls into OCCT, Clipper2, and OpenCAMLib through bindings. For a greenfield project whose first milestone is edge and face deburring, that is much less risky than trying to recreate mature CAD geometry in Rust from scratch. citeturn11search1turn11search6turn14search0turn10search0turn14search2

## The recommendation I would make

The most logical choice is to build a **standalone Python CAM kernel around OCCT**, and let FreeCAD become only one client of that kernel rather than the place where the kernel lives. Start with OCCT bindings for STEP/B-Rep access, Clipper2 for 2D boundary work, OpenCAMLib as an optional cutter-projection helper, and a custom machine-kinematics/posture module tailored to indexed and simultaneous use cases. Add FCL or PyBullet when you are ready for real collision and holder-clearance checking. That technology mix gives you the shortest credible path from **deburring through edges and faces** to later **3+2, 4+1, and full 5-axis surface milling**. citeturn11search6turn11search1turn14search0turn14search2turn10search0turn6search6turn7search0

If I compress the entire research into a single decision: **do not start from OpenMill, BlenderCAM, FreeCAD Path, or a generic robotics planner as your kernel base**. Study them, borrow ideas from them, and perhaps interface with them. But make your actual kernel depend first on **OCCT for geometry**, **your own contact/posture logic**, and **a small number of narrow supporting libraries** that each solve a well-defined job. That is the architecture most likely to survive the transition from “deburring edges now” to “serious multiaxis CAM later.” citeturn13view0turn16view2turn8search0turn8search20turn11search12turn3search0

A very sensible first internal module layout would be: **geometry**, **tool models**, **contact solver**, **tool-axis solver**, **collision**, **machine kinematics**, and **post**. With that structure, your first release can be a deburring kernel, your second can do indexed 3+2 and 4+1, and your third can grow into full simultaneous 5-axis and then surface finishing. The libraries above do not remove the need to design that kernel, but they let you avoid reimplementing the most expensive foundations from scratch. citeturn11search12turn14search0turn10search0turn5search19turn13view0






flowchart LR
    A[Job Spec] --> B[Geometry I/O]
    B --> C[Feature Graph]
    C --> D[Sampler]
    D --> E[Contact Solver]
    E --> F[Posture Solver]
    F --> G[Machine IK]
    G --> H[Collision and Gouge]
    H --> I[Smoothing and Feed Planning]
    I --> J[Postprocessor]
    J --> K[NC Output]

    L[Tool Library] --> E
    M[Machine Model] --> G
    M --> H
    N[Stock and Fixtures] --> H
    O[Test and Regression Assets] --> B
    O --> H






Layer	Recommended choice
Prototype language	Python
Production orchestration	Rust
Native heavy geometry/collision modules	C++
Geometry kernel	OCCT via OCP first, native OCCT later
Contact solver	OpenCAMLib
Collision engine	FCL
2D offsets and clipping	Clipper2
Mesh utilities	trimesh first, libigl later
Kinematics	custom NTX solver first, Pinocchio later
Rust math	nalgebra primary, glam optional
Browser/UI inspiration	Kiri:Moto pattern, not Kiri core
Engines to study but not embed as core	PyCAM, FreeCAD Path, BlenderCAM






cam_kernel/
  pyproject.toml
  README.md
  jobs/
    ntx2500_demo_edge_deburr.yaml
  cam_kernel/
    __init__.py
    api/
      job_schema.py
      tool_schema.py
      machine_schema.py
    geometry/
      occt_session.py
      step_io.py
      topology_graph.py
      tessellation_cache.py
      feature_extract.py
    sampling/
      edge_sampler.py
      face_sampler.py
      local_frames.py
    tools/
      cutter_models.py
      holder_models.py
      engagement_rules.py
    contact/
      ocl_bridge.py
      local_contact.py
    posture/
      axis_seed.py
      posture_cost.py
      posture_opt.py
    kinematics/
      ntx2500_model.py
      ntx2500_ik.py
      branch_selector.py
    collision/
      fcl_scene.py
      gouge_checks.py
      machine_envelope.py
    smoothing/
      pose_filter.py
      joint_filter.py
      feed_plan.py
    post/
      fanuc_ntx_post.py
      formatters.py
    viz/
      backplot.py
      debug_export.py
  native/
    rust/
      Cargo.toml
      src/
        lib.rs
        posture_cost.rs
        joint_smoothing.rs
    cpp/
      CMakeLists.txt
      fcl_bridge.cpp
      occt_bridge.cpp
      ocl_bridge.cpp
  tests/
    unit/
    geometry_regression/
    machine_proving/







flowchart TD
    A[MVP prototype] --> B[OCCT topology and feature graph]
    B --> C[Edge and face deburr seeds]
    C --> D[OpenCAMLib contact layer]
    D --> E[Custom NTX IK]
    E --> F[FCL holder and fixture collision]
    F --> G[Indexed 3+2 proving]
    G --> H[v1 continuous 5-axis deburring]
    H --> I[Posture optimization and smoothing]
    I --> J[Machine regression suite]
    J --> K[v2 surface finishing expansion]
    K --> L[Pinocchio-based multi-machine abstraction]
    K --> M[Advanced stock and rest logic]






Release	Core features	Deliverables	Acceptance criteria	Estimated effort
MVP	STEP intake, OCCT feature graph, selected edge/face deburring, ball/cone tools, indexed 3+2 posture, custom NTX post, basic holder/fixture collision	Python prototype, regression parts, backplot, first air-cut NC on NTX	Stable import of representative parts, repeatable edge deburr paths, no post syntax faults in dry-run, no obvious collision in simulation/air cut	10–14 weeks
v1	Continuous 5-axis deburring on edge chains and local face paths, posture cost optimization, branch continuity, FCL collision integration, joint-space smoothing	Hybrid Python + native modules, machine regression suite, first metal proving on selected coupons	No branch-flip failures on regression set, acceptable burr-break/chamfer size on proving coupons, stable runtime on representative jobs, no gouges in validated test parts	16–24 weeks after MVP
v2	Expansion to 4+1 and surface finishing, richer tool-axis controls, optional Pinocchio machine abstraction, mesh/B-Rep mixed workflows, stronger stock-aware checks	Production-capable kernel API, larger proving library, comparison against one commercial CAM benchmark on selected parts	Reliable finishing/deburr on representative geometry classes, stable post across proven machine modes, regression suite covering deburr + finishing cases	24–36 weeks after v1






{
  "machine": "DMG_MORI_NTX2500",
  "family": "turn_mill",
  "controller_frontend": "MAPPS / verify exact version on machine",
  "controller_backend": "Fanuc-family or other builder option; verify",
  "units": "mm",
  "post_mode": "mill_turn_5x",
  "kinematics": {
    "linear_axes": ["X", "Y", "Z"],
    "rotary_axes": ["B", "C"],
    "tcp_required": true,
    "axis_order_preference": ["X", "Y", "Z", "B", "C"]
  },
  "format": {
    "xyz_decimals": 3,
    "abc_decimals": 3,
    "feed_decimals": 1
  },
  "safety": {
    "cancel_modes": ["G40", "G49", "G80"],
    "absolute_mode": "G90",
    "metric_mode": "G21",
    "safe_plane": "G17"
  },
  "tcp": {
    "enable": "VERIFY_MACHINE_SPECIFIC",
    "disable": "VERIFY_MACHINE_SPECIFIC"
  },
  "spindle": {
    "cw": "M3",
    "ccw": "M4",
    "stop": "M5"
  },
  "coolant": {
    "on": "M8",
    "off": "M9"
  },
  "tool_change": {
    "command": "M6",
    "length_offset_prefix": "H"
  }
}






