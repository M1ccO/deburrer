from fc_deburr.domain.models import (
    CutDirection,
    FeatureLoop,
    FeatureSample,
    MotionKind,
    Operation,
    PathPoint,
    Toolpath,
)
from fc_deburr.features.wire import prepare_wire_loop
from fc_deburr.solver.transforms import apply_spring_passes


def _sample(x):
    return FeatureSample(
        position=(float(x), 0.0, 0.0),
        tangent=(1.0, 0.0, 0.0),
        guide_normal=(0.0, 1.0, 0.0),
        other_normal=(0.0, 0.0, 1.0),
    )


def test_reverse_cut_direction_reverses_open_feature_and_tangents():
    loop = FeatureLoop(
        id="open",
        samples=tuple(_sample(index) for index in range(3)),
        closed=False,
    )

    prepared = prepare_wire_loop(
        loop,
        Operation(
            id="reverse",
            tool_id="tool",
            cut_direction=CutDirection.REVERSE,
        ),
        subdivide_for_posture=False,
    )

    assert [sample.position[0] for sample in prepared.samples] == [2.0, 1.0, 0.0]
    assert all(sample.tangent == (-1.0, 0.0, 0.0) for sample in prepared.samples)
    assert prepared.reversed_from_selection


def test_reverse_closed_feature_preserves_selected_start():
    loop = FeatureLoop(
        id="closed",
        samples=tuple(_sample(index) for index in range(4)),
        closed=True,
    )

    prepared = prepare_wire_loop(
        loop,
        Operation(
            id="reverse",
            tool_id="tool",
            cut_direction=CutDirection.REVERSE,
        ),
        subdivide_for_posture=False,
    )

    assert [sample.position[0] for sample in prepared.samples] == [
        0.0,
        3.0,
        2.0,
        1.0,
    ]


def test_spring_pass_repeats_safe_path_and_scales_cut_feed():
    path = Toolpath(
        feature_id="feature",
        operation_id="operation",
        tool_id="tool",
        points=(
            PathPoint(0, (0, 0, 5), (0, 0, 1), MotionKind.RAPID),
            PathPoint(
                1,
                (0, 0, 0),
                (0, 0, 1),
                MotionKind.APPROACH,
                feed=400.0,
            ),
            PathPoint(
                2,
                (10, 0, 0),
                (0, 0, 1),
                MotionKind.CUT,
                feed=800.0,
            ),
            PathPoint(3, (10, 0, 5), (0, 0, 1), MotionKind.RETRACT),
        ),
    )

    transformed = apply_spring_passes(
        path,
        Operation(
            id="spring",
            tool_id="tool",
            spring_passes=2,
            spring_feed_fraction=0.5,
        ),
    )

    assert len(transformed.points) == len(path.points) * 3
    assert [point.seq for point in transformed.points] == list(
        range(len(transformed.points))
    )
    assert transformed.points[4].motion is MotionKind.RAPID
    assert transformed.points[5].feed == 200.0
    assert transformed.points[6].feed == 400.0
    assert "spring_pass=1" in transformed.points[6].flags
    assert transformed.points[8].motion is MotionKind.RAPID
