from dataclasses import replace

from fc_deburr.domain.models import FeatureLoop
from fc_deburr.machine.profiles import MachineProfile
from fc_deburr.machine.validation import validate_feature


def test_large_tangent_jump_blocks_feature(circular_feature):
    samples = list(circular_feature.samples)
    samples[5] = replace(samples[5], tangent=(0.0, 0.0, 1.0))
    broken = FeatureLoop(
        id="broken",
        samples=tuple(samples),
        closed=True,
        source_object_id=circular_feature.source_object_id,
    )

    report = validate_feature(broken, MachineProfile())

    assert not report.ok
    assert any(issue.code == "feature.tangent_jump" for issue in report.issues)


def test_source_wire_corner_is_detected_even_if_stored_tangent_is_smoothed():
    from fc_deburr.domain.models import FeatureSample

    smooth_tangent = (1.0, 0.0, 0.0)
    samples = (
        FeatureSample((0.0, 0.0, 0.0), smooth_tangent, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        FeatureSample((1.0, 0.0, 0.0), smooth_tangent, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        FeatureSample((1.0, 1.0, 0.0), smooth_tangent, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        FeatureSample((0.0, 1.0, 0.0), smooth_tangent, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    )
    report = validate_feature(
        FeatureLoop(id="square", samples=samples, closed=True),
        MachineProfile(),
    )

    assert any(issue.code == "feature.chord_jump" for issue in report.issues)
