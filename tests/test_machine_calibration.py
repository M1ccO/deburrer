import pytest

from fc_deburr.machine.kinematics import (
    axis_machine_from_b,
    axis_model_from_bc,
    bc_from_axis_model,
    model_to_machine,
)
from fc_deburr.machine.profiles import MachineProfile


def test_model_to_machine_axis_calibration_fixture():
    profile = MachineProfile()

    assert model_to_machine((1.0, 0.0, 0.0), profile) == (0.0, 0.0, 1.0)
    assert model_to_machine((0.0, 1.0, 0.0), profile) == (0.0, 1.0, 0.0)
    assert model_to_machine((0.0, 0.0, 1.0), profile) == (1.0, 0.0, 0.0)


def test_b_zero_is_radial_and_b_minus_90_is_main_face_axial():
    profile = MachineProfile()

    assert axis_machine_from_b(0.0, profile) == pytest.approx(
        (1.0, 0.0, 0.0)
    )
    assert axis_machine_from_b(-90.0, profile) == pytest.approx(
        (0.0, 0.0, 1.0)
    )


def test_positive_and_negative_c_rotate_part_axis_oppositely():
    profile = MachineProfile()

    plus = axis_model_from_bc(0.0, 90.0, profile)
    minus = axis_model_from_bc(0.0, -90.0, profile)

    assert model_to_machine(plus, profile) == pytest.approx(
        (0.0, 1.0, 0.0), abs=1.0e-10
    )
    assert model_to_machine(minus, profile) == pytest.approx(
        (0.0, -1.0, 0.0), abs=1.0e-10
    )


@pytest.mark.parametrize(
    "b_deg,c_deg",
    [
        (0.0, 0.0),
        (-45.0, 30.0),
        (25.0, -90.0),
        (-89.0, 170.0),
    ],
)
def test_bc_vector_round_trip(b_deg, c_deg):
    profile = MachineProfile()
    axis = axis_model_from_bc(b_deg, c_deg, profile)

    actual_b, actual_c = bc_from_axis_model(
        axis, profile, preferred_c_deg=c_deg
    )

    assert actual_b == pytest.approx(b_deg)
    assert actual_c == pytest.approx(c_deg)
