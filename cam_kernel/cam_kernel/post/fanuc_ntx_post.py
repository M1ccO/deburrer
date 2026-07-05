"""FANUC NTX post-processor.

Renders validated machine toolpaths as G-code for the FANUC 31i-B5
controller on DMG MORI NTX series machines.  Supports:

- TCP programming via G43.4
- B-axis contouring control (M594/M595)
- C-axis engage/disengage (M45/M46)
- B-axis clamp/unclamp (M368/M369)
- Diameter programming (X doubled from radius)
- Modal output (repeated B/C/fixed F emitted once)
- Spindle and coolant control

Format conventions:
- XYZ to 3 decimals, ABC to 3 decimals, F to 1 decimal
- G00 for rapid/retract, G01 for feed moves
- Line-by-line motion-kind comments

Bridges to ``fc_deburr.machine.post_ntx.post_ntx_tcp``.

TODO:
 - G41.2/G42.2 5-axis radius compensation
 - G68.2 tilted working plane
 - G54.4 WSEC fixture offsets
 - Probing cycles (G31)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class NtxPostSettings:
    program_number: int = 1000
    tool_code: str = "T01"
    work_offset: str = "G54"
    h_offset: int = 1
    tcp_d: int = 9
    tool_change_b_deg: float = -90.0
    tool_change_d: int = 0
    spindle_speed: Optional[int] = None
    spindle_direction: str = "M03"
    coolant_on: bool = False
    coolant_off_code: str = "M9"
    extra_preamble: Tuple[str, ...] = ()
    extra_footer: Tuple[str, ...] = ()


def post_ntx_tcp(machine_toolpath, settings: NtxPostSettings) -> str:
    """Render a machine toolpath as FANUC NTX G-code.

    Delegates to ``fc_deburr.machine.post_ntx.post_ntx_tcp``.
    """
    from fc_deburr.machine.post_ntx import post_ntx_tcp as _post, NtxPostSettings as _Settings
    from fc_deburr.machine.profiles import MachineProfile

    profile = MachineProfile(id="ntx_tcp_provisional", diameter_programming=True)
    fc_settings = _Settings(
        program_number=settings.program_number,
        tool_code=settings.tool_code,
        work_offset=settings.work_offset,
        h_offset=settings.h_offset,
        tcp_d=settings.tcp_d,
        tool_change_b_deg=settings.tool_change_b_deg,
        tool_change_d=settings.tool_change_d,
        spindle_speed=settings.spindle_speed,
        spindle_direction=settings.spindle_direction,
        coolant_on=settings.coolant_on,
        coolant_off_code=settings.coolant_off_code,
        extra_preamble=settings.extra_preamble,
        extra_footer=settings.extra_footer,
    )
    return _post(machine_toolpath, profile, fc_settings)
