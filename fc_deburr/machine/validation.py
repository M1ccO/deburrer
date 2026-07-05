from __future__ import annotations

import math

from ..domain.models import (
    FeatureLoop,
    MachineToolpath,
    ValidationIssue,
    ValidationReport,
    ISSUE_B_LIMIT,
    ISSUE_B_STEP,
    ISSUE_C_LIMIT,
    ISSUE_C_STEP,
)
from ..geometry.vectors import angle_deg, dot, normalize, sub
from .profiles import MachineProfile


def validate_feature(
    loop: FeatureLoop, profile: MachineProfile
) -> ValidationReport:
    issues = []
    if not loop.closed:
        issues.append(ValidationIssue("feature.open", "Feature loop is not closed"))
    if len(loop.samples) < 3:
        issues.append(
            ValidationIssue("feature.too_short", "Feature requires at least 3 samples")
        )
        return ValidationReport(tuple(issues))

    count = len(loop.samples)
    for index, current in enumerate(loop.samples):
        previous_sample = loop.samples[(index - 1) % count]
        following = loop.samples[(index + 1) % count]
        incoming_chord = sub(current.position, previous_sample.position)
        outgoing_chord = sub(following.position, current.position)
        chord_jump = angle_deg(incoming_chord, outgoing_chord)
        if chord_jump > profile.max_tangent_jump_deg:
            issues.append(
                ValidationIssue(
                    "feature.chord_jump",
                    "Source wire changes %.2f degrees at a sample" % chord_jump,
                    index,
                )
            )
        tangent_jump = angle_deg(current.tangent, following.tangent)
        if tangent_jump > profile.max_tangent_jump_deg:
            issues.append(
                ValidationIssue(
                    "feature.tangent_jump",
                    "Tangent changes %.2f degrees" % tangent_jump,
                    index,
                )
            )
        guide_jump = angle_deg(current.guide_normal, following.guide_normal)
        other_jump = angle_deg(current.other_normal, following.other_normal)
        if max(guide_jump, other_jump) > profile.max_normal_jump_deg:
            issues.append(
                ValidationIssue(
                    "feature.normal_jump",
                    "Face normal changes %.2f degrees"
                    % max(guide_jump, other_jump),
                    index,
                )
            )
        tangent = normalize(current.tangent)
        if abs(dot(tangent, normalize(current.guide_normal))) > 1.0e-3:
            issues.append(
                ValidationIssue(
                    "feature.guide_not_perpendicular",
                    "Guide normal is not perpendicular to the edge tangent",
                    index,
                )
            )
        if abs(dot(tangent, normalize(current.other_normal))) > 1.0e-3:
            issues.append(
                ValidationIssue(
                    "feature.other_not_perpendicular",
                    "Other normal is not perpendicular to the edge tangent",
                    index,
                )
            )
    return ValidationReport(tuple(issues))


def validate_machine_path(
    path: MachineToolpath, profile: MachineProfile
) -> ValidationReport:
    issues = []
    previous = None
    for index, point in enumerate(path.points):
        values = point.xyz_radius + (point.b_deg, point.c_deg)
        if not all(math.isfinite(value) for value in values):
            issues.append(
                ValidationIssue(
                    "machine.non_finite",
                    "Machine point contains a non-finite value",
                    index,
                )
            )
        if not profile.b_min_deg <= point.b_deg <= profile.b_max_deg:
            issues.append(
                ValidationIssue(
                    ISSUE_B_LIMIT,
                    "B %.3f is outside %.3f..%.3f; choose another "
                    "indexed posture, motion mode, part side, or recalibrate "
                    "the provisional B sign/zero"
                    % (
                        point.b_deg,
                        profile.b_min_deg,
                        profile.b_max_deg,
                    ),
                    index,
                )
            )
        if (
            profile.c_min_deg is not None
            and point.c_deg < profile.c_min_deg
        ) or (
            profile.c_max_deg is not None
            and point.c_deg > profile.c_max_deg
        ):
            issues.append(
                ValidationIssue(
                    "machine.c_limit",
                    "C %.3f is outside configured limits" % point.c_deg,
                    index,
                )
            )
        if previous is not None:
            b_step = abs(point.b_deg - previous.b_deg)
            c_step = abs(point.c_deg - previous.c_deg)
            if b_step > profile.max_b_step_deg:
                issues.append(
                    ValidationIssue(
                        ISSUE_B_STEP,
                        "B changes %.3f degrees in one sample" % b_step,
                        index,
                    )
                )
            # C step is a *warning* by default: the C value is derived from
            # the wire tangent and the wire can be coarsely sampled at
            # sharp corners.  Block on it only when the machine profile is
            # marked as strictly calibrated.
            if c_step > profile.max_c_step_deg:
                issues.append(
                    ValidationIssue(
                        ISSUE_C_STEP,
                        "C changes %.3f degrees in one sample (sample %d). "
                        "The wire may be under-sampled at a corner; "
                        "consider re-extracting with a smaller spacing."
                        % (c_step, index),
                        index,
                        is_error=bool(profile.calibrated),
                    )
                )
        previous = point
    return ValidationReport(tuple(issues))
