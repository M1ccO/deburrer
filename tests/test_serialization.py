from dataclasses import replace

from fc_deburr.domain.models import (
    FacePatch,
    FaceRegion,
    FeatureLoop,
    FeatureSample,
)
from fc_deburr.domain.serialization import (
    face_region_from_document,
    face_region_to_document,
    feature_loop_from_document,
    feature_loop_to_document,
)


def test_feature_document_round_trip(circular_feature):
    document = feature_loop_to_document(circular_feature)

    restored = feature_loop_from_document(document)

    assert restored == circular_feature
    assert document["schema"] == "fc_deburr.feature_loop"
    assert document["schema_version"] == 1


def test_feature_document_rejects_unknown_schema(circular_feature):
    document = feature_loop_to_document(circular_feature)
    document["schema_version"] = 99

    try:
        feature_loop_from_document(document)
    except ValueError as error:
        assert "schema version" in str(error)
    else:
        raise AssertionError("unknown schema version was accepted")


def test_wire_center_and_source_kind_round_trip(circular_feature):
    centered = replace(circular_feature, center_xyz=(1.0, 2.0, 3.0))

    restored = feature_loop_from_document(
        feature_loop_to_document(centered)
    )

    assert restored == centered
    assert restored.source_kind.value == "wire"


def test_face_region_round_trip():
    region = FaceRegion(
        id="face",
        patches=(FacePatch("Face1", "BREP SNAPSHOT", 12.5),),
        center_xyz=(1.0, 2.0, 3.0),
        source_object_id="Body",
    )

    restored = face_region_from_document(face_region_to_document(region))

    assert restored == region


def test_two_sample_open_feature_round_trip():
    sample = FeatureSample(
        position=(0.0, 0.0, 0.0),
        tangent=(1.0, 0.0, 0.0),
        guide_normal=(0.0, 1.0, 0.0),
        other_normal=(0.0, 0.0, 1.0),
    )
    feature = FeatureLoop(
        id="single-open-edge",
        samples=(
            sample,
            replace(sample, position=(1.0, 0.0, 0.0)),
        ),
        closed=False,
    )

    restored = feature_loop_from_document(
        feature_loop_to_document(feature)
    )

    assert restored == feature
