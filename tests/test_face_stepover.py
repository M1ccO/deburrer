import pytest

from fc_deburr.domain.errors import GeometryError
from fc_deburr.freecad_adapter.face_finishing import ball_stepover


def test_ball_stepover_comes_from_scallop_height():
    assert ball_stepover(3.0, 0.05) == pytest.approx(
        2.0 * (2.0 * 3.0 * 0.05 - 0.05**2) ** 0.5
    )


def test_ball_stepover_rejects_impossible_tolerance():
    with pytest.raises(GeometryError):
        ball_stepover(3.0, 3.0)
