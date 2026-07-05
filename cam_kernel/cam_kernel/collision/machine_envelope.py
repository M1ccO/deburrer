"""Machine envelope — axis limit and workspace boundary checks.

Validates that the entire toolpath stays within:
- B-axis soft limits (configurable, typically ±120°)
- C-axis limits (if applicable; NTX C is unlimited)
- Linear axis travel limits (X, Y, Z)
- Tool-change clearance envelope (holder must clear the part at index)

Runs as part of the validation pass before NC posting.

Bridges to ``fc_deburr.machine.validation.validate_machine_path``.

TODO:
 - Linear axis travel envelope checking
 - Tool-change clearance validation
 - Dynamic limits (velocity, acceleration, jerk)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class EnvelopeReport:
    ok: bool
    violations: Tuple[str, ...] = ()

    @property
    def error_count(self) -> int:
        return len(self.violations)


def check_machine_envelope(machine_points, b_limits: tuple, xyz_limits=None) -> EnvelopeReport:
    """Check all machine points against axis limits.

    Delegates to ``fc_deburr.machine.validation``.
    """
    from fc_deburr.machine.validation import validate_machine_path
    from fc_deburr.machine.profiles import MachineProfile

    profile = MachineProfile(
        b_min_deg=b_limits[0],
        b_max_deg=b_limits[1],
    )
    from fc_deburr.domain.models import MachineToolpath

    path = MachineToolpath(
        feature_id="envelope_check",
        operation_id="",
        tool_id="",
        points=tuple(machine_points),
    )
    report = validate_machine_path(path, profile)
    return EnvelopeReport(
        ok=report.ok,
        violations=tuple(issue.message for issue in report.issues),
    )
