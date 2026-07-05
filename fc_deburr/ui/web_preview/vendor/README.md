Vendored Three.js libraries
============================

Three.js r161 (MIT)
- three.module.min.js  — Core 3D rendering library
- OrbitControls.js     — Mouse orbit/pan/zoom controls

To update:
  1. Pick a tag from https://github.com/mrdoob/three.js/releases
  2. Replace these files from the corresponding CDN:
     https://unpkg.com/three@<version>/build/three.module.min.js
     https://unpkg.com/three@<version>/examples/jsm/controls/OrbitControls.js
  3. Update the version number below and commit.

Current version: 0.161.0
Last updated: 2026-07-05
