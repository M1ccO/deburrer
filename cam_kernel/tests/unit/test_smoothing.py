"""Unit tests for smoothing (pose filter, joint filter, feed plan)."""

from __future__ import annotations

from cam_kernel.smoothing.pose_filter import ema_smooth_axes, angular_velocity
from cam_kernel.smoothing.joint_filter import moving_average_smooth, check_joint_steps


class TestPoseFilter:
    def test_ema_empty(self):
        assert ema_smooth_axes([]) == []

    def test_ema_single(self):
        axes = [(1.0, 0.0, 0.0)]
        result = ema_smooth_axes(axes)
        assert len(result) == 1
        assert abs(result[0][0] - 1.0) < 1e-10

    def test_ema_reduces_noise(self, sample_axes):
        noisy = [
            (1.0, 0.05, 0.02),
            (0.7, 0.71, -0.02),
            (0.01, 1.0, 0.01),
            (-0.71, 0.7, 0.03),
            (-0.99, 0.02, 0.0),
        ]
        result = ema_smooth_axes(noisy, alpha=0.3)
        assert len(result) == len(noisy)

    def test_angular_velocity(self, sample_axes):
        velocities = angular_velocity(sample_axes)
        assert len(velocities) == len(sample_axes)
        assert velocities[0] == 0.0


class TestJointFilter:
    def test_ma_empty(self):
        b, c = moving_average_smooth([], [])
        assert b == []
        assert c == []

    def test_ma_identity_w1(self):
        b_in = [10.0, 20.0, 30.0]
        c_in = [50.0, 60.0, 70.0]
        b, c = moving_average_smooth(b_in, c_in, window=1)
        assert b == b_in
        assert c == c_in

    def test_check_joint_steps_no_warning(self):
        b = [0.0, 5.0, 10.0]
        c = [0.0, 10.0, 20.0]
        warnings = check_joint_steps(b, c)
        assert len(warnings) == 0

    def test_check_joint_steps_exceeds(self):
        b = [0.0, 25.0]
        c = [0.0, 50.0]
        warnings = check_joint_steps(b, c)
        assert len(warnings) == 2
