"""Kinematics layer — machine-specific IK and branch selection.

Owns the forward and inverse kinematics for the NTX2500 table-table
mill-turn configuration.  The kinematics model is layered:

1. **Model** — axis mapping, sign conventions, limits (``ntx2500_model.py``)
2. **IK** — tool-axis to B/C mapping (``ntx2500_ik.py``)
3. **Branch selector** — deterministic branch selection for redundant
   solutions (``branch_selector.py``)

The kinematics are reversible by construction:

- ``axis_model_from_bc(b, c)`` → part-space tool axis
- ``bc_from_axis_model(axis)`` → B/C machine angles

All functions are pure — they receive a profile/machine definition and
return values without side effects.

Bridges to ``fc_deburr.machine.kinematics`` which already implements
the full NTX kinematics pipeline.
"""
