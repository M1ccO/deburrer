"""Unit tests for NC formatters and debug export."""

from __future__ import annotations

import json
import os
import tempfile

from cam_kernel.post.formatters import (
    format_number,
    format_xyz,
    format_bc,
    program_header,
    program_footer,
)
from cam_kernel.viz.debug_export import export_points_json, export_csv


class TestFormatters:
    def test_format_number_integer(self):
        assert format_number(123.0, 3) == "123"

    def test_format_number_trailing_zeros(self):
        assert format_number(12.300, 3) == "12.3"

    def test_format_number_zero(self):
        assert format_number(0.0, 3) == "0"

    def test_format_number_negative(self):
        assert format_number(-5.1, 2) == "-5.1"

    def test_format_xyz(self):
        result = format_xyz(10.0, 20.0, 30.0)
        assert "X10" in result
        assert "Y20" in result
        assert "Z30" in result

    def test_format_bc_repeated(self):
        result = format_bc(45.0, 90.0, 45.0, 90.0)
        assert result == ""

    def test_format_bc_new_values(self):
        result = format_bc(45.0, 90.0, None, None)
        assert "B45" in result
        assert "C90" in result

    def test_program_header(self):
        h = program_header(1234, "TEST")
        assert "O1234" in h
        assert "TEST" in h

    def test_program_footer(self):
        assert program_footer() == "M30\n"


class TestDebugExport:
    def test_export_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("[]")
            path = f.name
        try:
            export_points_json([{"x": 1.0, "y": 2.0}], path)
            with open(path) as fh:
                data = json.load(fh)
            assert len(data) == 1
            assert data[0]["x"] == 1.0
        finally:
            os.unlink(path)
