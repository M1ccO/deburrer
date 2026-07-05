"""Post layer — NC code generation.

Owns text formatting only.  Receives validated machine toolpaths and
renders them as G-code programs for specific controllers.

Current backends:
- ``fanuc_ntx_post.py`` — FANUC MAPPS / 31i-B5 controller for NTX 2500

Future backends:
- Heidenhain TNC
- Siemens 840D
- Haas NGC
- LinuxCNC

All post-processors use the same validated ``MachineToolpath`` as input.
The post layer never modifies geometry, B/C values, or feed rates — it
is a pure renderer.

Bridges to ``fc_deburr.machine.post_ntx`` which already implements
the full FANUC NTX TCP post with G43.4, M594/M595, etc.
"""
