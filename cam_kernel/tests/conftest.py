"""Shared pytest configuration for the CAM kernel test suite.

Run with::

    cd cam_kernel && pytest
"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_edge_samples():
    """Three simple edge samples forming a 90-degree corner."""
    from cam_kernel.sampling.edge_sampler import EdgeSample

    return (
        EdgeSample(
            position=(0.0, 0.0, 0.0),
            tangent=(1.0, 0.0, 0.0),
            guide_normal=(0.0, 1.0, 0.0),
            other_normal=(0.0, 0.0, 1.0),
            edge_id="e1",
        ),
        EdgeSample(
            position=(10.0, 0.0, 0.0),
            tangent=(1.0, 0.0, 0.0),
            guide_normal=(0.0, 1.0, 0.0),
            other_normal=(0.0, 0.0, 1.0),
            edge_id="e1",
        ),
        EdgeSample(
            position=(10.0, 10.0, 0.0),
            tangent=(0.0, 1.0, 0.0),
            guide_normal=(0.0, 0.0, 1.0),
            other_normal=(-1.0, 0.0, 0.0),
            edge_id="e2",
        ),
    )


@pytest.fixture
def ntx2500_config():
    from cam_kernel.kinematics.ntx2500_model import Ntx2500Config

    return Ntx2500Config()


@pytest.fixture
def sample_axes():
    return [
        (1.0, 0.0, 0.0),
        (0.707, 0.707, 0.0),
        (0.0, 1.0, 0.0),
        (-0.707, 0.707, 0.0),
        (-1.0, 0.0, 0.0),
    ]
