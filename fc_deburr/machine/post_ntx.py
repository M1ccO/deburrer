from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..domain.errors import ValidationError
from ..domain.models import MachineToolpath, MotionKind
from .profiles import MachineProfile
from .validation import validate_machine_path


@dataclass(frozen=True)
class NtxPostSettings:
    program_number: int
    tool_code: str
    work_offset: str = "G54"
    h_offset: int = 1
    tcp_d: int = 9
    tool_change_b_deg: float = -90.0
    tool_change_d: int = 0
    spindle_speed: int | None = None
    spindle_direction: str = "M03"
    coolant_on: bool = False
    coolant_off_code: str = "M9"
    extra_preamble: Tuple[str, ...] = ()
    extra_footer: Tuple[str, ...] = ()


def post_ntx_tcp(
    path: MachineToolpath,
    profile: MachineProfile,
    settings: NtxPostSettings,
) -> str:
    report = validate_machine_path(path, profile)
    if not report.ok:
        messages = "; ".join(issue.message for issue in report.issues)
        raise ValidationError("Refusing to post invalid machine path: " + messages)
    if not path.points:
        raise ValidationError("Refusing to post an empty machine path")

    lines = [
        "O%04d (DEBURR TCP)" % settings.program_number,
        "(MACHINE PROFILE %s%s)"
        % (
            profile.id.upper(),
            "" if profile.calibrated else " - CALIBRATION REQUIRED",
        ),
        settings.work_offset,
        "G52 C0.",
        "%s (TOOL SELECTION)" % settings.tool_code,
        "M45 (C-AXIS ON)",
        "G00 C0.",
        "G361 B%s D%d."
        % (_number(settings.tool_change_b_deg, 3), settings.tool_change_d),
        "G43 H%d." % settings.h_offset,
        "G49",
        "G43.4 D%d" % settings.tcp_d,
        "M594 (B-AXIS CONTOUR ON)",
        "M369 (B-AXIS COUPLING OFF)",
    ]
    if settings.spindle_speed is not None:
        if settings.spindle_speed <= 0:
            raise ValidationError("Spindle speed must be positive")
        if settings.spindle_direction not in ("M03", "M04"):
            raise ValidationError("Spindle direction must be M03 or M04")
        lines.append(
            "S%d %s" % (settings.spindle_speed, settings.spindle_direction)
        )
    if settings.coolant_on:
        lines.append("M08")
    lines.extend(settings.extra_preamble)
    lines.append("(--------------------------)")

    last_b = None
    last_c = None
    feed_emitted = False
    for point in path.points:
        gcode = "G00" if point.motion in (MotionKind.RAPID, MotionKind.RETRACT) else "G01"
        x, y, z = point.xyz_radius
        if profile.diameter_programming:
            x *= 2.0
        words = [
            gcode,
            "X%s" % _number(x, 4),
            "Y%s" % _number(y, 4),
            "Z%s" % _number(z, 4),
        ]
        if last_b is None or abs(point.b_deg - last_b) > 0.0005:
            words.append("B%s" % _number(point.b_deg, 3))
        if last_c is None or abs(point.c_deg - last_c) > 0.0005:
            words.append("C%s" % _number(point.c_deg, 3))
        if gcode == "G01" and point.feed is not None and not feed_emitted:
            words.append("F%s" % _number(point.feed, 3))
            feed_emitted = True
        words.append("(%s)" % point.motion.value.upper())
        lines.append(" ".join(words))
        last_b = point.b_deg
        last_c = point.c_deg

    lines.extend(
        [
            "(--------------------------)",
            "M595 (B-AXIS CONT. OFF)",
            "G49 (TOOL OFFSET OFF)",
            "G53 X0 Y0. %s" % settings.coolant_off_code,
            "G53 Z0 M5",
            "M46 (C-AXIS OFF)",
            "G0 B%s" % _number(settings.tool_change_b_deg, 3),
            "M368 (B-AXIS CLAMP ON)",
        ]
    )
    lines.extend(settings.extra_footer)
    lines.extend(["M01", "M30"])
    return "\n".join(lines) + "\n"


def _number(value: float, decimals: int) -> str:
    text = ("%.*f" % (decimals, value)).rstrip("0").rstrip(".")
    if text in ("-0", ""):
        return "0"
    return text
