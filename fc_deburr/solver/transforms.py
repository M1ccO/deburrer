from __future__ import annotations

from dataclasses import replace

from ..domain.errors import GeometryError
from ..domain.models import MotionKind, Operation, Toolpath


def apply_spring_passes(
    path: Toolpath,
    operation: Operation,
) -> Toolpath:
    """Repeat a complete, safely retracted path at a reduced feed.

    The duplicated pass begins with the original safe rapid, so every repeat
    traverses between pass endpoints above the part instead of connecting them
    with an unintended cutting move.
    """
    count = int(operation.spring_passes)
    if count <= 0:
        return path
    if count > 10:
        raise GeometryError("Spring pass count must be between 0 and 10")
    fraction = float(operation.spring_feed_fraction)
    if not 0.0 < fraction <= 1.0:
        raise GeometryError(
            "Spring pass feed fraction must be greater than 0 and at most 1"
        )
    if not path.points:
        raise GeometryError("Cannot add a spring pass to an empty toolpath")
    if path.points[0].motion is not MotionKind.RAPID:
        raise GeometryError("Spring passes require a safe rapid at path start")
    if path.points[-1].motion is not MotionKind.RETRACT:
        raise GeometryError("Spring passes require a safe retract at path end")

    points = list(path.points)
    original = path.points
    feed_motions = {
        MotionKind.APPROACH,
        MotionKind.LEAD_IN,
        MotionKind.CUT,
        MotionKind.LEAD_OUT,
    }
    for pass_index in range(1, count + 1):
        for point in original:
            feed = point.feed
            if feed is not None and point.motion in feed_motions:
                feed *= fraction
            points.append(
                replace(
                    point,
                    seq=len(points),
                    feed=feed,
                    flags=point.flags + (
                        "spring_pass=%d" % pass_index,
                        "spring_feed_fraction=%.6f" % fraction,
                    ),
                )
            )
    return replace(
        path,
        points=tuple(points),
        warnings=path.warnings
        + (
            "%d spring pass(es) at %.1f%% feed"
            % (count, fraction * 100.0),
        ),
    )
