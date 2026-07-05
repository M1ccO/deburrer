"""Unit tests for tool and machine schemas."""

from __future__ import annotations

import pytest

from cam_kernel.api.tool_schema import (
    CutterDefinition,
    HolderDefinition,
    ToolAssembly,
    ToolKind,
)
from cam_kernel.api.machine_schema import (
    MachineDefinition,
    MachineTopology,
    ntx2500_default,
)


class TestCutterDefinition:
    def test_ball_cutter(self):
        cutter = CutterDefinition(
            id="ball_6mm",
            kind=ToolKind.BALL,
            diameter=6.0,
            stickout=30.0,
            tip_radius=3.0,
        )
        assert cutter.kind == ToolKind.BALL
        assert cutter.diameter == 6.0

    def test_chamfer_cutter(self):
        cutter = CutterDefinition(
            id="chamfer_90",
            kind=ToolKind.CHAMFER,
            diameter=8.0,
            stickout=40.0,
            included_angle_deg=90.0,
            tip_flat_diameter=0.5,
        )
        assert cutter.kind == ToolKind.CHAMFER
        assert cutter.included_angle_deg == 90.0


class TestMachineDefinition:
    def test_ntx2500_default(self):
        machine = ntx2500_default()
        assert machine.id == "ntx_tcp_provisional"
        assert machine.family == MachineTopology.TURN_MILL
        assert len(machine.linear_axes) == 3
        assert len(machine.rotary_axes) == 2
        assert machine.rotary_axes[1].unlimited

    def test_rotary_axis_limits(self):
        machine = ntx2500_default()
        b_axis = machine.rotary_axes[0]
        assert b_axis.name == "B"
        assert b_axis.min_deg == -120.0
        assert b_axis.max_deg == 120.0
