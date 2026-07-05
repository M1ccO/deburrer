# NTX Deburr Engine

## Wire Deburr

1. In FreeCAD, select one closed wire or its connected edges.
2. Run `Deburr_Feature_to_Job.FCMacro`.
3. Choose sample spacing and direction. The macro calculates the old-style
   wire bounding-box center and automatically places C0 at the +Y radial
   extreme.
4. Select or edit a cutter preset, set chamfer width or ball engagement, then
   press **CALCULATE AND VALIDATE**.
5. Inspect source/contact/cutter/safe paths and the B/C range before saving NC.

Choose the machine motion explicitly:

- **True 3+2** indexes one B/C posture before approach and holds both axes
  fixed throughout the cut.
- **4+1** holds indexed C while B follows the cut.
- **5-Axis Simultaneous** permits both B and C to follow the cut.

Indexed modes calculate a suggested posture by default. Disable
**Calculate indexed angles** to enter B/C manually. A chamfer operation is
blocked when the selected mode cannot preserve cone tangency over the loop.

Chamfer size is equal width along both adjoining faces. Ball mode creates a
rounded break controlled by engagement and reports predicted face extents.

**Tangent Positioning** approaches along the contour tangent. **Center
Positioning** uses the calculated center-to-C0 radial direction for approach
and retract. It does not cut all the way from the center. Use **Flip calculated
deburr side** when the virtual wire frame points to the wrong side.

## Face Finishing

1. In FreeCAD, select one or more target faces only.
2. Run `Deburr_Feature_to_Job.FCMacro`; no wire or vertex is required.
3. The app switches to Ball tool mode.
4. Set **Maximum scallop height**, pass direction, and point spacing.
5. Calculate and inspect the generated zigzag passes before saving NC.

The stepover is calculated from ball radius `R` and maximum scallop height `h`
as `2 × sqrt(2Rh - h²)`, so a smoother requested finish automatically creates
more passes.

## Verification

Run:

```powershell
.\verify.ps1
```

This runs dependency-free solver tests, golden NTX output checks, Python compile
checks, and a real FreeCAD topology/extraction integration check.

The current kinematic profile is intentionally named `ntx_tcp_provisional`.
Complete calibration-shape and machine air-cut validation before using its NC
output on a part. Its provisional convention is B0 radial, B-90 axial for
main-spindle end-face work, and C+ clockwise when viewed from the tool side
toward the main chuck.
