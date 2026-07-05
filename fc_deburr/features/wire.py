import math
from dataclasses import replace

from ..domain.models import (
    CutDirection,
    FeatureLoop,
    FeatureSample,
    Operation,
    PositioningMode,
)
from ..geometry.vectors import dot, normalize, scale


def _subdivide_at_corners(
    samples: tuple,
    closed: bool,
    max_tangent_step_deg: float = 3.0,
    max_iter: int = 10,
) -> tuple:
    """Insert midpoints where the tangent changes more than ``max_tangent_step_deg``.

    The tangent in model space is the feature's own ``sample.tangent``, which
    the toolpath engine will transform through ``model_to_machine`` to derive C.
    Subdividing here makes the C value change smoothly because the underlying
    segments are shorter at corners, and the monotonic unwrap can do its job
    without large jumps.
    """
    for _ in range(max_iter):
        count = len(samples)
        new_samples = []
        segment_count = count if closed else count - 1
        for i in range(segment_count):
            new_samples.append(samples[i])
            cur = samples[i]
            nxt = samples[(i + 1) % count]
            step = _angle_between(cur.tangent, nxt.tangent)
            if step <= max_tangent_step_deg:
                continue
            t = 0.5
            mid_pos = tuple(cur.position[k] + (nxt.position[k] - cur.position[k]) * t for k in range(3))
            # Average, then re-orthonormalise against the tangent.
            mid_tan = _normalize_or(
                tuple(cur.tangent[k] + nxt.tangent[k] for k in range(3)),
                cur.tangent,
            )
            raw_guide = tuple(cur.guide_normal[k] + nxt.guide_normal[k] for k in range(3))
            raw_other = tuple(cur.other_normal[k] + nxt.other_normal[k] for k in range(3))
            mid_guide = _orthogonalize(raw_guide, mid_tan)
            mid_other = _orthogonalize(raw_other, mid_tan)
            new_samples.append(
                replace(
                    cur,
                    position=mid_pos,
                    tangent=mid_tan,
                    guide_normal=mid_guide,
                    other_normal=mid_other,
                    source_edge_id="resampled",
                )
            )
        if not closed:
            new_samples.append(samples[-1])
        if len(new_samples) == count:
            return tuple(new_samples)
        samples = new_samples
    return tuple(samples)


def _angle_between(a: tuple, b: tuple) -> float:
    dot_val = sum(a[k] * b[k] for k in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot_val))))


def _normalize_or(v, fallback):
    mag = math.sqrt(sum(c * c for c in v))
    if mag < 1e-9:
        return fallback
    return tuple(c / mag for c in v)


def _orthogonalize(v, normal):
    """Remove the component of ``v`` parallel to ``normal``, then normalize."""
    proj = dot(v, normal)
    v_out = tuple(v[k] - proj * normal[k] for k in range(3))
    return _normalize_or(v_out, normal)


def prepare_wire_loop(
    loop: FeatureLoop,
    operation: Operation,
    subdivide_for_posture: bool = True,
) -> FeatureLoop:
    """Return an operation-specific view without mutating exported geometry."""

    samples = loop.samples
    reversed_for_cut = operation.cut_direction is CutDirection.REVERSE
    if reversed_for_cut:
        if loop.closed:
            samples = samples[:1] + tuple(reversed(samples[1:]))
        else:
            samples = tuple(reversed(samples))
        samples = tuple(
            replace(
                sample,
                tangent=tuple(-component for component in sample.tangent),
            )
            for sample in samples
        )
    if subdivide_for_posture:
        samples = _subdivide_at_corners(samples, closed=loop.closed)

    if operation.positioning_mode is PositioningMode.CENTER:
        if not loop.closed:
            raise ValueError(
                "Center Positioning requires a closed feature; "
                "use Tangent Positioning for an open edge chain"
            )
        if loop.center_xyz is None:
            raise ValueError("Center Positioning requires a calculated wire center")
        center = loop.center_xyz
        # Model Y is the C0 reference direction for the established NTX model
        # mapping (model Y -> machine Y). Model Z breaks symmetric ties.
        start_index = max(
            range(len(samples)),
            key=lambda index: (
                samples[index].position[1] - center[1],
                samples[index].position[2] - center[2],
            ),
        )
        samples = samples[start_index:] + samples[:start_index]

    if operation.flip_side:
        samples = tuple(
            replace(
                sample,
                guide_normal=tuple(
                    -component for component in sample.guide_normal
                ),
                other_normal=tuple(
                    -component for component in sample.other_normal
                ),
            )
            for sample in samples
        )
    return replace(
        loop,
        samples=tuple(samples),
        reversed_from_selection=(
            loop.reversed_from_selection ^ reversed_for_cut
        ),
    )
