# OpenMill Feature Gap Map

This document uses the public
[OpenMill feature list](https://github.com/charlatanshost/OpenMill#openmill-)
as a product checklist only. NTX Deburr does not use OpenMill as a library,
extension, code dependency, or project format.

Status date: 2026-07-05.

| Feature group | NTX Deburr status | Next implementation gate |
|---|---|---|
| STEP/B-Rep geometry | Implemented through OCCT/OCP | Stable topology fingerprints across changed STEP revisions |
| Manual feature picking | Face and edge picking implemented in the web viewport | Connected-edge flood fill, multi-face regions, selection filters |
| Feature recognition | First valid face is suggested automatically | Hole, pocket, ruled-wall, concave-corner classification |
| Edge deburring | Ball/chamfer solvers support open and closed connected chains; indexed ball paths preserve the sphere center through corners | Target-side visualization, multiple disconnected chains, rest passes |
| Face finishing | Selected-face OCP zigzag with scallop-derived stepover | Parallel/scallop/spiral/rotary patterns and island-aware trimming |
| 3+2 / 4+1 / 5-axis modes | Implemented; indexed ball deburring chooses one fixed B/C after contact geometry is built | Collision-aware posture search, multi-region indexing and optimized transitions |
| Roughing strategies | Not implemented | Stock-aware adaptive and simultaneous roughing |
| Pocket / contour / pencil / swarf / geodesic | Not implemented | Add only after feature graph and stock contracts are stable |
| Drilling / tapping / thread milling | Not implemented | Hole recognition, cycle schemas, and controller proving |
| Common strategy transforms | Linear lead-in/out, safety lift, forward/reverse cut direction, and safely retracted spring passes | Model-space range clipping and reusable arc/ramp leads |
| Tool management | Current-job ball/chamfer form only | Persistent library, holder profiles, material feed/speed presets |
| Machine management | One provisional NTX profile | Persistent calibrated machines, travel/pivot/post defaults |
| Stock and model setup | Optional stock/fixture STL for checking | Parametric stock, model translation, origin/centering controls |
| Plan/simulation views | 3D part, path, tool poses and trail | Separate plan/simulation modes and swept material removal |
| Collision | Optional FCL part/holder/fixture checks | Swept-volume sampling, visible collision markers, mandatory gate |
| Verification | Machine-path limits/step checks and diagnostics | Unified pre-export verifier covering stock, feeds and collisions |
| Estimates | Job/path metrics implemented | Acceleration-aware operation and job totals |
| Post-processing | Provisional Fanuc NTX TCP post | Post interface, inverse time, LinuxCNC reference, proven NTX variant |
| Job persistence | Versioned validated job JSON plus ordered B-Rep edge-operation execution | Web save/open, combined multi-operation post, assets bundle |
| Autosave / undo / setup sheet | Not implemented | Add after the job command/state model exists |

## Delivery order

1. **Viewport and selection** — visible STEP model, face/edge ray picking,
   topology-backed feature replacement. Implemented in the current slice.
2. **Persistent job backbone** — tool library, machine library, save/load,
   autosave and undoable state changes.
3. **Stock and recognition** — parametric stock plus hole/pocket/ruled-surface
   feature extraction.
4. **Strategy expansion** — indexed clearing, pocketing, drilling and richer
   face finishing.
5. **Simulation and production verification** — swept material removal,
   collision visualization, controller-specific post proving and setup sheets.

Every strategy must use the same selected B-Rep feature IDs, machine profile,
verification gate and versioned job document. A UI control without those
contracts does not count as an implemented CAM capability.
