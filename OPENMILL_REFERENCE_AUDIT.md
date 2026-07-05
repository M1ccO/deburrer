# OpenMill Reference Audit

Reference inspected: `charlatanshost/OpenMill` commit
`e5220c9dd5fbe4f048ee2eeb92c1d2037b8370a4` (2026-05-11).

OpenMill is used only as a product and architecture reference. NTX Deburr does
not import, vendor, execute, or extend OpenMill code.

## What was inspected

- `openmill-core`: job, tool, machine, feature, verification, kinematics,
  toolpath, leads, all strategy modules, and common transforms.
- `openmill-post`: post trait, Fanuc/LinuxCNC/GRBL implementations, and
  inverse-time feed handling.
- `openmill-sim`: collision primitives.
- `openmill-ui`: operation dispatch, background generation, autosave,
  undo/redo, project bundle, setup sheet, viewport, and voxel simulation.
- README, guide, contribution conventions, and persisted tool examples.

## Architectural conclusions

### Keep NTX Deburr's geometry foundation

OpenMill is mesh-first. Its recognition and many strategy decisions use
triangle normals, flood fills, raycasts, AABBs, or sampled mesh queries. NTX
Deburr's OCCT STEP/B-Rep topology, exact adjacent faces, analytic surfaces,
and explicit contact geometry are the better foundation for deburring and
multiaxis finishing.

The OpenMill strategy implementations are useful prototypes and UX references,
but they are not a substitute for B-Rep-aware cutter contact, gouge checking,
or machine-proven NTX posture solving.

### Adopt the workflow contracts natively

The most reusable ideas are contracts rather than algorithms:

1. A versioned job owns ordered operations, feature references, tools, machine,
   fixtures, stock, process defaults, and post settings.
2. Operations reference stable feature and tool IDs rather than UI state.
3. Cross-strategy transforms are applied consistently.
4. Toolpath verification gates NC export.
5. Tool and machine libraries are persistent records.
6. Long-running generation is cancellable and reports operation-level progress.
7. Save/load, autosave, undo/redo, and portable bundles operate on the same job
   document.

## Current native gap map

| Contract | NTX Deburr status after this audit | Next gate |
|---|---|---|
| STEP/B-Rep geometry | Stronger than reference | Stable fingerprints across revised STEP files |
| Versioned job | Implemented in `cam_kernel.api.job_schema` | Web save/open and portable asset bundle |
| Ordered operations | Persisted, validated, and executed sequentially for B-Rep edge operations | Face-strategy integration and combined post |
| Feature references | Stable face/edge IDs in one STEP session | Revision reconciliation and disconnected chain groups |
| Common transforms | Forward/reverse direction and safe spring passes | Model-space range clipping and reusable arc/ramp leads |
| Tool records | Ball/chamfer runtime schema, holder schema skeleton | Persistent library, presets, more cutter families |
| Machine records | NTX schema and provisional profile | Persistent calibrated profiles and dynamic limits |
| Verification | Geometry and machine checks exist | One pre-export report including collision and feed policy |
| Feature recognition | First-face suggestion only | B-Rep holes, pockets, ruled walls, blends, and edge classes |
| Strategies | Edge deburr and selected-face zigzag | Drilling, contour/pocket, rest machining, richer finishing |
| Simulation | Path/tool animation and optional FCL checks | Swept removal, stock state, mandatory collision gate |
| Persistence UX | Job JSON kernel contract | Autosave, undo/redo, project bundle, setup sheet |

## Delivery tranches

1. **Job execution and verification**
   - Extend the ordered executor from edge operations to face strategies.
   - Aggregate operation metrics.
   - Run one structured verifier before combined NC export.
   - Refuse export on hard errors; retain warnings with source indices.

2. **Persistent resources**
   - Tool library with holder profile, flute count, presets, and lifecycle data.
   - Calibrated machine library with travel, rotary, velocity, and post
     capabilities.
   - Portable project bundle containing the job, STEP model, fixtures, stock,
     tools, and machine snapshot.

3. **B-Rep feature graph**
   - Connected edge-chain groups, including multiple disconnected operations.
   - Hole and pocket recognition from topology and analytic surfaces.
   - Convex/concave edge classification, blend detection, and target-side
     previews.

4. **Strategy expansion**
   - Drilling and tapping from recognized cylindrical features.
   - 2.5D contour/pocket paths from planar B-Rep wires.
   - Rest-aware roughing and finishing.
   - Scallop, parallel, pencil, swarf, and geodesic-style surface strategies
     implemented against OCCT geometry.

5. **Production simulation**
   - Swept cutter/holder collision with visible markers.
   - Stock removal state shared across ordered operations.
   - Machine-motion timing and controller-proven post capabilities.

## Rule for future gap work

Feature parity means matching the manufacturing capability and workflow
contract, not reproducing OpenMill's implementation. Every new strategy must
use NTX Deburr's selected B-Rep IDs, immutable contact data, machine profile,
structured verifier, and versioned job document.
