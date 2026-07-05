from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PRESETS = {
    "90° chamfer D6": {
        "kind": "chamfer",
        "tool_id": "C90",
        "diameter": 6.0,
        "stickout": 25.0,
        "included_angle": 90.0,
        "tip_flat": 0.0,
        "contact_radius": 0.5,
        "radial_correction": 0.0,
        "axial_correction": 0.0,
    },
    "Ball D6": {
        "kind": "ball",
        "tool_id": "B6",
        "diameter": 6.0,
        "stickout": 25.0,
        "radial_correction": 0.0,
        "axial_correction": 0.0,
    },
}


class ToolPresetStore:
    """Owns user-editable tool definitions; widgets receive copies only."""

    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".fc_deburr_tools.json"
        self._user = self._load_user()

    def names(self):
        return tuple(DEFAULT_PRESETS) + tuple(
            name for name in sorted(self._user) if name not in DEFAULT_PRESETS
        )

    def get(self, name):
        source = self._user.get(name, DEFAULT_PRESETS.get(name))
        return dict(source) if source is not None else None

    def save(self, name, values):
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Preset name cannot be empty")
        self._user[clean_name] = dict(values)
        self._write()

    def _load_user(self):
        try:
            with open(self.path, encoding="utf-8") as stream:
                value = json.load(stream)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            json.dump(self._user, stream, indent=2)
