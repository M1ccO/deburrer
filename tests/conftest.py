import math

import pytest

from fc_deburr.domain.models import FeatureLoop, FeatureSample


@pytest.fixture
def circular_feature():
    samples = []
    count = 24
    radius = 10.0
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        radial = (math.cos(angle), math.sin(angle), 0.0)
        samples.append(
            FeatureSample(
                position=(radius * radial[0], radius * radial[1], 0.0),
                tangent=(-radial[1], radial[0], 0.0),
                guide_normal=(0.0, 0.0, 1.0),
                other_normal=radial,
                source_edge_id="Edge1",
            )
        )
    return FeatureLoop(
        id="circle",
        samples=tuple(samples),
        closed=True,
        source_object_id="Cylinder",
        source_edge_ids=("Edge1",),
        guide_face_id="Face1",
        c0_vertex_id="Vertex1",
    )
