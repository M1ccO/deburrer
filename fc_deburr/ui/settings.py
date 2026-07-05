from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".fc_deburr_ui.json"


def load_ui_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as stream:
            value = json.load(stream)
            return (
                migrate_ui_settings(value)
                if isinstance(value, dict)
                else {}
            )
    except (OSError, ValueError):
        return {}


def save_ui_settings(value):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
    except OSError:
        pass


def migrate_ui_settings(value):
    migrated = dict(value)
    if "motion_mode" not in migrated:
        migrated["motion_mode"] = (
            "simultaneous_5_axis"
            if migrated.get("c_axis_mode") == "simultaneous"
            else "indexed_3_plus_2"
        )
    return migrated
