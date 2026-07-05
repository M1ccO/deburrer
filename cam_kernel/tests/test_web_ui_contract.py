from pathlib import Path


STATIC_DIR = Path(__file__).parents[1] / "cam_kernel" / "web" / "static"


def test_model_fetch_and_renderer_have_distinct_names():
    index_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    viewer_source = (STATIC_DIR / "viewer.js").read_text(encoding="utf-8")
    assert "async function fetchModelMesh(sid)" in index_source
    assert "window.renderModelMesh = renderModelMesh" in viewer_source
    assert "window.loadModelMesh" not in index_source
    assert "window.loadModelMesh" not in viewer_source


def test_topology_selection_contract_is_wired_on_both_sides():
    index_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    viewer_source = (STATIC_DIR / "viewer.js").read_text(encoding="utf-8")
    assert "/selection" in index_source
    assert "window.getTopologySelection" in viewer_source
    assert "window.setTopologySelectionMode" in viewer_source
    assert "triangle_face_indices" in viewer_source


def test_common_operation_transform_controls_are_exposed():
    index_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'name="cut_direction"' in index_source
    assert 'name="spring_passes"' in index_source
    assert 'name="spring_feed_fraction"' in index_source


def test_ball_operation_uses_face_width_not_ambiguous_center_infeed():
    index_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    viewer_source = (STATIC_DIR / "viewer.js").read_text(encoding="utf-8")

    assert 'name="ball_break_width"' in index_source
    assert 'name="ball_engagement"' not in index_source
    assert "buildCutCylinders(d);" not in viewer_source


def test_indexed_ball_controls_and_light_preview_are_wired():
    index_source = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    viewer_source = (STATIC_DIR / "viewer.js").read_text(encoding="utf-8")

    assert "syncIndexedBallControls" in index_source
    assert 'id="lead-deg-input"' in index_source
    assert 'id="tilt-deg-input"' in index_source
    assert "B0 or B±90" in index_source
    assert "#c8d1d7" in viewer_source
