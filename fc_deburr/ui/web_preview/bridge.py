from __future__ import annotations

from PySide6.QtCore import QObject, Slot, Signal


class PreviewBridge(QObject):
    previewLoaded = Signal(str)
    playIndexSet = Signal(int)
    playingToggled = Signal(bool)
    speedAdjusted = Signal(float)
    resetClicked = Signal()
    fitCameraClicked = Signal()

    @Slot(str)
    def loadPreview(self, json_string: str) -> None:
        pass

    @Slot(int)
    def setPlayIndex(self, index: int) -> None:
        pass

    @Slot(bool)
    def setPlaying(self, playing: bool) -> None:
        pass

    @Slot(float)
    def setSpeed(self, factor: float) -> None:
        pass

    @Slot()
    def reset(self) -> None:
        pass

    @Slot()
    def fitCamera(self) -> None:
        pass
