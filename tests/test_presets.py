from fc_deburr.ui.presets import ToolPresetStore


def test_preset_store_returns_copies_and_persists(tmp_path):
    path = tmp_path / "tools.json"
    store = ToolPresetStore(path)
    values = {
        "kind": "chamfer",
        "tool_id": "CUSTOM",
        "diameter": 8.0,
        "stickout": 30.0,
        "included_angle": 90.0,
        "tip_flat": 0.2,
        "contact_radius": 1.0,
    }
    store.save("My tool", values)
    returned = store.get("My tool")
    returned["diameter"] = 999.0

    restored = ToolPresetStore(path)

    assert restored.get("My tool")["diameter"] == 8.0
    assert "90° chamfer D6" in restored.names()
