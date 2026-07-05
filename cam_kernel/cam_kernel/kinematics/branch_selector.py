"""Branch selector — deterministic branch identification for redundant IK.

For table-table kinematics with unlimited C-axis, multiple (B, C) pairs
can produce the same tool axis.  The branch selector:

1. Enumerates kinematically valid branches at each station.
2. Assigns each branch a stable integer identity.
3. Penalizes branch changes in the global optimization.
4. Resolves ambiguous cases (e.g., B near 0) with hysteresis.

The primary branch is always the one returned by ``bc_from_axis_model``
with no wrapping.  Secondary branches are computed by reflecting C
through 180° and adjusting B accordingly.

Bridges to ``fc_deburr.machine.kinematics`` which already implements
C-continuity unwrapping via ``_nearest_equivalent``.

TODO:
 - Multi-branch enumeration for all redundant solutions
 - Hysteresis for branch stability near singularities
 - Branch identification for non-NTX topologies
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Tuple


class BranchID(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    UNKNOWN = "unknown"


def identify_branch(b_deg: float, c_deg: float, c_equivalent: Optional[float] = None) -> BranchID:
    """Identify whether the (B,C) pair is the primary or secondary branch.

    The primary branch uses C closest to 0 (or to the preferred value).
    The secondary branch is offset by ±180° in C with compensated B.

    TODO: Implement branch identification.
    """
    return BranchID.PRIMARY


def enumerate_branches(
    axis_model, kinematics, preferred_c: Optional[float] = None
) -> List[Tuple[float, float, BranchID]]:
    """Enumerate all valid (B, C, branch) tuples for a tool axis.

    TODO: Full branch enumeration.
    """
    raise NotImplementedError("Branch enumeration not yet implemented")
