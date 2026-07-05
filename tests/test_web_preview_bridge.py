from fc_deburr.ui.web_preview.bridge import PreviewBridge


def test_bridge_instantiation():
    bridge = PreviewBridge()
    assert bridge is not None


def test_bridge_calls_do_not_crash():
    bridge = PreviewBridge()
    bridge.loadPreview('{"test": true}')
    bridge.setPlayIndex(5)
    bridge.setPlaying(True)
    bridge.setSpeed(2.5)
    bridge.reset()
    bridge.fitCamera()


def test_bridge_signals_exist():
    bridge = PreviewBridge()
    assert hasattr(bridge, "previewLoaded")
    assert hasattr(bridge, "playIndexSet")
    assert hasattr(bridge, "playingToggled")
    assert hasattr(bridge, "speedAdjusted")
    assert hasattr(bridge, "resetClicked")
    assert hasattr(bridge, "fitCameraClicked")
