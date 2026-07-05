# Deburr Engine Architecture

## Data ownership

The engine uses immutable records between layers. A layer never edits data
owned by an earlier layer.

1. `freecad_adapter` temporarily owns FreeCAD `TopoShape` objects. It exports a
   wire as a `FeatureLoop` containing plain tuples. Selected finishing faces
   are exported as immutable `FaceRegion` BREP snapshots so the separate
   FreeCAD-backed surface solver can evaluate them after the document closes.
2. `domain` owns immutable source geometry, tool definitions, operations, and
   path value types.
3. `solver` reads a `FeatureLoop` and creates the authoritative analytic
   contact solution. Source wire points are never moved.
   - Ball tool: cutter reference is the contact point on the part (not the ball
     center). The ball center is `radius` above the cutter reference along the
     tool axis.
   - Chamfer tool: cutter reference is the contact point on the chamfer face.
4. `kernel` adapts that solution into part-space posture candidates, evaluates
   feasibility, expands machine-space alternatives, and selects one continuous
   sequence. The current analytic solvers provide exactly one candidate per
   station, preserving their output.
5. `machine` creates a separate `MachineToolpath` through a kinematics backend.
   Model-space XYZ is never overwritten with remapped or diameter-mode values.
6. `post_ntx` renders validated machine data. It owns text formatting only.
7. `preview` transforms validated pipeline output into renderer-neutral display
   DTOs (`PreviewDocument`). The tool pose carries two axis representations:
   `tool_axis` (C-rotated, physical axis in model space) and `tool_axis_b_only`
   (B-only, unrotated axis in model space). Both are used by the 3D viewer and
   payload serialization.
8. `ui/web_preview` owns the Three.js-based 3D viewer (see section below).
   It is a renderer that consumes `PreviewDocument`, never the solver or post.
9. `DeburrSession` is the sole mutable application owner. Loading a new feature
   clears its path, preview, and NC output atomically.
10. UI widgets display or collect values. They do not own geometry or calculated
    paths.

## Module seams

| Module | Responsibility | Dependencies |
|--------|---------------|-------------|
| `domain/` | Immutable contracts: `FeatureLoop`, `FaceRegion`, `ToolDefinition`, `Operation`, `PathPoint`, `MachinePoint`, `Toolpath`, `MachineToolpath`, enums (`MotionMode`, `ToolKind`, `MotionKind`), versioned JSON serialization | None |
| `geometry/` | Vector math: `normalize`, `add`, `scale`, `sub`, `cross`, `rotate_about_axis` | None |
| `freecad_adapter/` | FreeCAD selection, topology extraction, C0 anchoring, sampling, face normals, BREP snapshots | FreeCAD |
| `features/` | Immutable feature views: Center Positioning, Flip Side | `domain` |
| `solver/` | Analytic chamfer/ball contact, approach/retract motion, posture realization per motion mode | `domain`, `geometry`, `features` |
| `kernel/` | Contact intent, tool assembly, posture-candidate graph, feasibility evaluation, candidate expansion, sequence selection | `domain`, `geometry` |
| `machine/` | Pluggable kinematics backends (`kinematics.py`), `MachineProfile` calibration, B/C inverse solution (`bc_from_axis_model`), forward axis model (`axis_model_from_bc`), safety validation, NTX postprocessor (`post_ntx.py`) | `domain`, `geometry` |
| `preview/` | Renderer-neutral DTOs: `PreviewDocument`, `PreviewPolyline`, `PreviewVector`, `PreviewMarker`, `PreviewToolGeometry`, `PreviewToolPose` | `domain`, `geometry`, `machine`, `application` |
| `ui/web_preview/` | Three.js 3D viewer: `WebPreviewWidget` (QWebEngineView + local HTTP server), `PreviewBridge` (QWebChannel), `payload.py` (PreviewDocument → JSON), `stl.py` (binary STL reader), `template.html` (Three.js scene) | `PySide6.QtWebEngineWidgets`, `PySide6.QtWebChannel`, vendored Three.js r161 |
| `ui/` | PySide widgets: `MainWindow`, `BackplotView` (2D top-down backplot), `RotaryPlotWidget` (B/C vs time), `ToolPresetStore`, `settings.py` | `preview`, `application` |
| `application/` | Use cases: `DeburrSession`, `calculate_toolpath`, `calculate_face_toolpath`, `PipelineResult`, `estimate_job` / `format_metrics` | `domain`, `solver`, `kernel`, `machine`, `features`, `preview` |
| `tools/` | Diagnostic scripts: `verify_5axis_c.py` | `domain`, `application`, `machine` |

FreeCAD cannot be imported by the domain, solver, machine, preview, or
application layers. NC formatting cannot be imported by geometry solvers.

## PreviewToolPose: dual axis representation

Each `PreviewToolPose` carries two tool axis vectors:

- **`tool_axis`** — the C-rotated physical axis in model space, computed via
  `axis_model_from_bc(b, c, profile)`. This is the tool's actual orientation
  after the C-axis workpiece rotation is factored in. Used by the 3D viewer
  when positioning the tool in world space (outside the C-rotated `partGroup`).

- **`tool_axis_b_only`** — the B-only axis in model space, computed via
  `axis_machine_from_b(b, profile)` → `machine_to_model(...)`. This is the
  tool orientation before C rotation. Used by the 3D viewer when the tool is
  placed inside the C-rotated `partGroup`, and by axis-vector rendering.

The `part_rotation_deg` field equals `-physical_c` and drives the C-axis
rotation applied to `partGroup` in the Three.js scene (see viewer layout below).

## Three.js 3D Viewer Layout

The viewer (rendered by `template.html`) uses a two-group scene:

1. **`partGroup`** (child of `scene`, rotated by `part_rotation_deg` around the
   spindle axis)
   - Workpiece mesh (STL, from `PreviewDocument.workpiece`)
   - Polylines: Source edge (`#00d7ff`), Guide-face boundary (`#43e0a3`),
     Other-face boundary (`#9bef5b`), Cutter contact (`#65e572`), Cutter
     reference (`#ffd23f`), Approach/Retract (`#ff6868`, dashed)
   - Axis vectors (B-only, `#b58cff`)
   - Markers (C0, wire center)
   - Semi-transparent cut tubes (`#ff4d4d`, 25% opacity) — one cylinder per
     CUT segment with the tool's diameter, showing the swept volume

2. **`toolGroup`** (child of `scene`, positioned at C-rotated cutter reference,
   oriented along `tool_axis` — the C-rotated axis)
   - Tool body: ball hemisphere (z=0 to z=radius) + shank cylinder (z=radius
     to z=stickout), both same color (`#c58b3b`)
   - Contact point marker (yellow sphere at z=0)
   - Tool axis arrow (purple `#b58cff`, length = stickout + max(2, diameter))

This layout ensures:
- The workpiece and polylines rotate with C (visualized as part rotation)
- The tool body is positioned in world space at the C-rotated contact point
- The tool orientation uses the C-rotated physical axis
- The axis vectors inside `partGroup` use the B-only axis (they inherit C
  rotation from the parent group)

## Tool body visualization

The **ball tool** body in the 3D viewer is rendered as two connected sections:

- **Ball hemisphere** (lower half of a full sphere, `THREE.SphereGeometry` with
  `thetaLength = π/2`): from local z=0 to z=radius. Center at `z=0`, dome
  extending upward. The flat bottom at z=0 is the contact point.
- **Shank cylinder** (`THREE.CylinderGeometry` with `rotation.x = π/2` to
  align the default Y-axis with the tool's Z-axis): from z=radius to
  z=stickout, same diameter (`2 * radius`) and same color as the ball.

The **chamfer tool** body consists of a tip flat disk, a conical cutting edge,
and a shank cylinder, all with `rotation.x = π/2` to align Y→Z.

A yellow contact-point marker sphere is placed at z=0 for both tool types.

## Material removal visualization

Semi-transparent red tubes (`#ff4d4d`, 25% opacity, `depthWrite: false`) are
built along every segment of the cutter reference polyline with the tool's
diameter. These tubes are children of `partGroup`, so they rotate with C and
show the tool's swept volume overlaid on the workpiece. No CSG or stencil
buffer is required — the visual overlay provides a clear picture of material
removal.

## Web preview architecture

The `ui/web_preview/` subpackage contains:

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `WebPreviewWidget` |
| `bridge.py` | `PreviewBridge` QObject (QWebChannel for future JS→Python calls) |
| `payload.py` | Converts `PreviewDocument` + STL path to JSON dict with Float32Arrays |
| `stl.py` | Binary STL reader (`read_binary_stl`) |
| `widget.py` | `WebPreviewWidget(QWidget)` — QWebEngineView, play/pause/scrub controls, local HTTP server lifecycle, `runJavaScript` for Python→JS communication |
| `template.html` | Self-contained Three.js scene: ES module imports from `vendor/`, scene graph, tool body, cut tubes, legend, controls |
| `vendor/` | Vendored Three.js r161 (`three.module.min.js`) and patched `OrbitControls.js` (imports changed from bare `'three'` to `'./three.module.min.js'`) |

**Communication flow**:
1. `widget.py` starts an `http.server.HTTPServer` on `127.0.0.1:0` serving
   from the `web_preview/` directory
2. `view.load(QUrl("http://127.0.0.1:PORT/template.html"))` loads the page
3. On `loadFinished`, the widget calls `view.page().runJavaScript(...)` to
   push JSON payloads and pose updates
4. Play/scrub is driven by a Python-side `QTimer` — the JS page is passive

**Fallback**: When `PySide6.QtWebEngineWidgets` is not available (e.g. in
FreeCAD's bundled Python), a `QLabel` placeholder is shown instead.

## Candidate pipeline

Wire deburring runs through these explicit stages:

1. Prepare and validate immutable source geometry.
2. Solve analytic ball or chamfer contact in part space.
3. Adapt each analytic point to a posture-candidate station.
4. Run a `FeasibilityBackend`. The default backend reports `not_checked`;
   it never claims that collision clearance passed.
5. Use a `MachineKinematicsBackend` to expand each part posture into machine
   candidates carrying B/C, branch identity, hard-limit margins, and soft-limit
   cost.
6. Select a deterministic global sequence using node and transition costs.
7. Convert the selection to the compatibility `Toolpath`, add explicit motion,
   solve the final `MachineToolpath`, validate, preview, and post.

## NTX motion modes and posture realization

`MotionMode` owns rotary freedom explicitly:

- **`indexed_3_plus_2`**: B and C are constant for the complete cutting loop.
  C0 is computed from the first tool axis. Both are held fixed.
- **`simultaneous_4_plus_1`**: C is constant (locked to the first tool axis
  azimuth) and B may vary. Suitable when C-axis rotation is undesirable but
  tilt variation is needed (e.g. cylindrical contours where B should follow
  the surface normal while C stays put).
- **`simultaneous_5_axis`**: both B and C may vary. For contours that wrap
  around the spindle axis (e.g. a groove on a cylinder), C naturally follows
  the tool-axis azimuth and may traverse 360°. This is correct kinematic
  behavior for 5-axis mode.

The analytic solver first owns contact intent. `solver/posture.py` then
recomputes the cutter-reference position from the posture that the selected
machine mode can physically realize. Ball posture changes preserve the ball
center. Chamfer posture changes must satisfy cone-plane tangency or posting is
blocked with the failing station.

### C-axis continuity in 5-axis mode

`bc_from_axis_model(...)` computes `physical_c = atan2(axis[1], axis[0])` and
uses `_nearest_equivalent(c, preferred_c)` to keep C continuous. This ensures
C unwraps without jumps, even when the tool-axis azimuth crosses ±180°. For a
closed contour that wraps around the spindle axis, C may vary by 360°+ over
the full loop — this is physically correct and should not be confused with a
wrapping bug.

## NTX kinematics convention

The kinematics are reversible:

- `axis_model_from_bc(b, c, profile)` — forward: computes the part-space tool
  axis from B/C machine angles. Applies C rotation to the machine-axis and
  converts to model coordinates.

- `axis_machine_from_b(b, profile)` — B-only axis in machine coordinates.
  B0 = radial +X, B-90 = axial +Z (away from main-spindle face).

- `bc_from_axis_model(axis_model, profile, preferred_c)` — inverse: computes
  B/C from a part-space tool axis. Returns the primary NTX branch.

The provisional convention is B0 radial, B-90 axial toward the main-spindle
end face, and C+ clockwise when viewed from the tool/subspindle side toward
the main chuck.

## ToolDefinition model

```python
@dataclass(frozen=True)
class ToolDefinition:
    id: str
    kind: ToolKind            # CHAMFER or BALL
    diameter: float           # cutting diameter (mm)
    stickout: float           # total tool length (mm)
    cutting_length: float     # cutting portion length; 0 = auto (2×diameter for ball)
    included_angle_deg: Optional[float]  # chamfer mill included angle
    tip_flat_diameter: float  # chamfer mill tip flat
    tip_radius: float         # ball endmill tip radius
    contact_radius: Optional[float]   # chamfer contact radius
    radial_correction: float  # calibration offset
    axial_correction: float   # calibration offset
```

`cutting_length` is exposed as a UI spinbox (displays "auto" when 0). It
controls the length of the cutting portion above the ball in the 3D preview.
At 0, a default of `2 × diameter` is used.

## The selector

Uses stable candidate IDs to break equal-cost ties. Its cost model
separates preferred-posture deviation, tool-axis motion, B/C motion,
soft-limit proximity, and branch changes. These terms are intentionally inert
with the current one-candidate analytic providers but are tested with synthetic
multi-candidate graphs.

`PipelineResult.kernel_diagnostics` exposes structured kernel status without
changing the UI contract. `collision.not_checked` means the current output
remains provisional and must not be interpreted as collision-cleared.

## Safety invariants

- Wire Deburr requires only a closed wire. Center, C0, and the mill-turn radial
  posture frame are derived automatically.
- Face Finishing requires only target faces and currently uses a ball tool.
- The selected source wire remains the contact-contour source of truth.
- Chamfer width offsets the cutter solution; global/radial contour scaling is
  not part of the new workflow.
- The selected start vertex emits cutting `C0`; C is then continuously
  unwrapped.
- Sharp source-wire or face-normal discontinuities block generation.
- Invalid B/C limits or steps block posting.
- Approach and retract are explicit path segments. There is no bounding-box
  center plunge and no automatic center-closing move.
- Chamfer tilt is blocked because it would invalidate the requested flat,
  equal-width chamfer. Lead rotation preserves cone-plane tangency.
- The current NTX transform remains a calibration profile. Machine use requires
  the agreed calibration shapes and an air-cut sign/zero check.
- `flip_side` reverses the cutter by negating **both** `guide_normal` and
  `other_normal` so the bisector truly flips 180°. The previous version only
  negated `other_normal`, which rotated the bisector 90° on every sample.

## FANUC 5-axis radius-compensation evidence

The available FANUC manual extract documents two distinct 5-axis tool-radius
offset formats:

- Type 1 uses `G41.2/G42.2` with endpoint `X Y Z B C`.
- Type 2 uses `G41.6/G42.6` with endpoint `X Y Z`, tool-axis direction
  `I J K`, and tool-angle gradient `Q`. It uses the table coordinate system,
  and B/C commands in this mode raise PS5460.

This confirms that tool axis belongs in the part-space kernel independently of
B/C. It does **not** by itself prove generic XYZ+IJK TCP programming under
`G43.4`; TCP positioning and 5-axis cutter-radius compensation remain separate
post capabilities.

The same extract requires reading the offset once at B-90 degrees and cancelling
it before enabling the 5-axis radius offset. It documents G00/G01 support and
PS5460 restrictions for unsupported interpolation or malformed I/J/K use.
These facts are recorded for a future capability-gated post only. The current
provisional NTX post and golden NC output remain frozen.

## Debugging

Inspect failures at the layer that owns the value:

- Wrong point order, normals, or C0: `freecad_adapter`.
- Wrong cutter offset/contact: `solver`.
- Correct model path but wrong B/C: `machine/kinematics.py` and its profile.
- Correct machine path but wrong text/modal behavior: `machine/post_ntx.py`.
- Correct values but wrong display: `preview/`, `ui/web_preview/template.html`,
  or `ui/backplot_view.py`.
- Tool body wrong in 3D view: `ui/web_preview/template.html` → `buildTool()`.
- Cut tubes not visible: `ui/web_preview/template.html` → `buildCutCylinders()`.
- C-axis wrapping excessively: verify feature geometry (contour around spindle)
  and consider `simultaneous_4_plus_1` instead of `simultaneous_5_axis`.

## Diagnostic tools

`tools/verify_5axis_c.py` — loads a feature JSON, runs the pipeline in 5-axis
mode, and prints B/C ranges, tool-axis values, and per-point diagnostics.
Asserts that C-axis varies (not constant) and reports the total span.

Run with: `python tools/verify_5axis_c.py [feature_file.json]`

## Job metrics and CAM-style summary

`application/job_metrics.py` derives a `JobMetrics` value from a validated
machine path: cut/rapid lengths, cycle estimate, B/C posture range, bisector
polar range, contact extents, and a list of human-readable notes (e.g. when
the source bisector exceeds the B envelope). `format_metrics(metrics, profile)`
renders a multi-line block used in the UI status tab.

## UI widgets

| Widget | File | Description |
|--------|------|-------------|
| `MainWindow` | `ui/main_window.py` | Main application window with control panel (feature, tool, operation, post), 3D viewer, tab panel |
| `WebPreviewWidget` | `ui/web_preview/widget.py` | Three.js 3D viewer (QWebEngineView). Play/pause/reset/scrub/speed controls. Emits `playIndexChanged` signal |
| `BackplotView` | `ui/backplot_view.py` | Top-down 2D backplot (QPainter). Renders source, contact, cutter path, trail, current tool position. Syncs via `playIndexChanged` |
| `RotaryPlotWidget` | `ui/rotary_plot.py` | B/C vs time plot |
| `ToolPresetStore` | `ui/presets.py` | Tool preset save/load |

Tab order: **Backplot** → **B/C Plot** → **Job Summary** → **NC Output**.

The `WebPreviewWidget.playIndexChanged` signal connects to `BackplotView.set_play_index`,
keeping the backplot synchronized with the 3D viewer's timeline.

## Removed files

The following legacy widgets were replaced by the web-based preview and
removed:

- `ui/cam_viewport.py` — QPainter-based 3D viewer (slow, pixelated during
  simulation, SW-rendered)
- `ui/toolpath_scene.py` — QGraphicsView-based 3D viewer (unused, replaced)

Legacy `deburr_tool.py` and `ntx_deburr_ui.py` remain available for comparison
but are not imported by the new engine.

## Running the application

`run.bat` launches the application using the **system Python** (not FreeCAD's
bundled Python), which provides `QtWebEngineWidgets` for the Three.js 3D viewer:

```
python deburr_app.py [feature_file.json]
```

The `verify.ps1` script runs the full test suite, compile checks, and FreeCAD
integration tests:

```powershell
.\verify.ps1
```

## Test inventory

| Test file | Coverage |
|-----------|----------|
| `tests/test_preview_builder_uses_bc.py` | `tool_axis` includes C rotation; `tool_axis_b_only` is B-only; `part_rotation_deg` matches physical C |
| `tests/test_motion_modes.py` | Preview poses match machine path block-for-block; chamfer posture realization for all modes |
| `tests/test_machine_calibration.py` | Kinematics forward/inverse round-trip; machine-to-model and reverse mapping |
| `tests/test_flip_side_and_validation.py` | Flip side reverses both normals; guide vectors remain perpendicular |
| `tests/test_tool_preview_geometry.py` | Payload structure, STL reader, cutting_length in payload, `_display_stl_path` selection |
| `tests/test_web_preview_bridge.py` | `PreviewBridge` slots and signals exist and don't crash |
| `tests/test_motion_mode_goldens.py` | Golden B/C values for known toolpaths |
| `tests/test_kernel_*.py` | Candidate graph, selection, machine backend, pipeline |

Currently **76 tests**, all passing.
