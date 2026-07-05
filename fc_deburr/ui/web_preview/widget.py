from __future__ import annotations

import functools
import http.server
import json
import socket
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QWidget

from ...preview.models import PreviewDocument, PreviewToolGeometry

_TEMPLATE_DIR = Path(__file__).resolve().parent

_WEBENGINE_AVAILABLE = False
try:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QPushButton,
        QSlider,
        QVBoxLayout,
    )
    _WEBENGINE_AVAILABLE = True
except ImportError:
    pass


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_static_server() -> int:
    port = _find_free_port()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(_TEMPLATE_DIR),
    )
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return port


if _WEBENGINE_AVAILABLE:
    from .bridge import PreviewBridge
    from .payload import build_json

    class WebPreviewWidget(QWidget):
        PLAY_MS = 70

        playIndexChanged = Signal(int)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setMinimumSize(560, 480)
            self.setToolTip(
                "Left-drag = orbit | Middle/Right = pan | Wheel = zoom"
            )

            self._port = _start_static_server()
            self._document: Optional[PreviewDocument] = None
            self._tool: Optional[PreviewToolGeometry] = None
            self._stl_path: Optional[str] = None
            self._play_index = 0
            self._play_speed = 1.0
            self._playing = False
            self._page_loaded = False

            self._bridge = PreviewBridge(self)
            self._channel = QWebChannel(self)
            self._channel.registerObject("bridge", self._bridge)

            self._view = QWebEngineView(self)
            self._view.setMinimumHeight(200)
            self._view.page().setWebChannel(self._channel)
            self._view.loadFinished.connect(self._on_page_loaded)

            self._slider = QSlider(Qt.Horizontal)
            self._slider.setMinimum(0)
            self._slider.setMaximum(0)
            self._slider.valueChanged.connect(self._on_slider)

            self._play_btn = QPushButton("Play")
            self._play_btn.clicked.connect(self.play)
            self._pause_btn = QPushButton("Pause")
            self._pause_btn.clicked.connect(self.pause)
            self._reset_btn = QPushButton("Reset")
            self._reset_btn.clicked.connect(self.reset)
            self._faster_btn = QPushButton("Faster")
            self._faster_btn.clicked.connect(self._faster)
            self._slower_btn = QPushButton("Slower")
            self._slower_btn.clicked.connect(self._slower)

            self._status = QLabel("No toolpath")
            self._status.setStyleSheet("color:#d7dde3;font-size:10pt;")
            self._speed_label = QLabel("1.0x")
            self._speed_label.setStyleSheet("color:#9aa4ad;font-size:10pt;")

            controls = QWidget()
            row = QHBoxLayout(controls)
            row.setContentsMargins(8, 4, 8, 4)
            row.addWidget(self._play_btn)
            row.addWidget(self._pause_btn)
            row.addWidget(self._reset_btn)
            row.addWidget(self._slower_btn)
            row.addWidget(self._faster_btn)
            row.addWidget(self._slider, stretch=1)
            row.addWidget(self._speed_label)
            row.addWidget(self._status)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(self._view, stretch=1)
            layout.addWidget(controls)

            self._timer = QTimer(self)
            self._timer.setInterval(int(self.PLAY_MS / max(0.1, self._play_speed)))
            self._timer.timeout.connect(self._advance)

            self._view.load(QUrl("http://127.0.0.1:%d/template.html" % self._port))

        def _on_page_loaded(self, ok: bool) -> None:
            if not ok:
                return
            self._page_loaded = True
            if self._document:
                self._send_payload()

        def _send_payload(self) -> None:
            if not self._page_loaded:
                self._status.setText("Page not loaded yet")
                return
            if not self._document:
                self._status.setText("No document")
                return
            try:
                json_str = build_json(self._document, self._stl_path)
            except Exception as exc:
                self._status.setText("Payload build failed: %s" % exc)
                return
            self._view.page().runJavaScript(
                "window.loadPayload(%s)" % json_str
            )
            self._update_slider_range()
            self._sync_buttons()

        def set_document(self, document: Optional[PreviewDocument]) -> None:
            self._document = document
            self.pause()
            self._play_index = 0
            self._send_payload()

        def set_tool(
            self,
            kind: str,
            diameter: float,
            stickout: float,
            cutting_length: float = 0.0,
            included_angle_deg: Optional[float] = None,
            tip_flat_diameter: float = 0.0,
        ) -> None:
            self._tool = PreviewToolGeometry(
                kind=str(kind),
                diameter=float(diameter),
                stickout=float(stickout),
                cutting_length=float(cutting_length),
                included_angle_deg=included_angle_deg,
                tip_flat_diameter=float(tip_flat_diameter),
            )

        def set_workpiece_stl(self, path: Optional[str]) -> None:
            self._stl_path = path
            if self._document:
                self._send_payload()

        def play(self) -> None:
            if not self._document or not self._document.tool_poses:
                return
            if self._play_index >= len(self._document.tool_poses) - 1:
                self._play_index = 0
            self._playing = True
            self._timer.start()
            self._sync_buttons()
            self._push_pose()

        def pause(self) -> None:
            self._playing = False
            self._timer.stop()
            self._sync_buttons()

        def reset(self) -> None:
            self._play_index = 0
            self._slider.setValue(0)
            self._sync_buttons()
            self._push_pose()

        def _advance(self) -> None:
            if not self._document or not self._document.tool_poses:
                self.pause()
                return
            self._play_index += 1
            count = len(self._document.tool_poses)
            if self._play_index >= count:
                self._play_index = count - 1
                self.pause()
            self._slider.setValue(self._play_index)

        def _on_slider(self, value: int) -> None:
            if not self._document or not self._document.tool_poses:
                return
            self._play_index = value
            self._update_status()
            self._push_pose()

        def _faster(self) -> None:
            self._play_speed = min(8.0, self._play_speed * 1.5)
            self._timer.setInterval(int(self.PLAY_MS / max(0.1, self._play_speed)))
            self._speed_label.setText("%.2fx" % self._play_speed)

        def _slower(self) -> None:
            self._play_speed = max(0.25, self._play_speed / 1.5)
            self._timer.setInterval(int(self.PLAY_MS / max(0.1, self._play_speed)))
            self._speed_label.setText("%.2fx" % self._play_speed)

        def _sync_buttons(self) -> None:
            has = bool(self._document and self._document.tool_poses)
            self._play_btn.setEnabled(has and not self._playing)
            self._pause_btn.setEnabled(self._playing)
            self._reset_btn.setEnabled(has)

        def _update_slider_range(self) -> None:
            if not self._document or not self._document.tool_poses:
                self._slider.setRange(0, 0)
            else:
                self._slider.setRange(0, len(self._document.tool_poses) - 1)
            self._update_status()

        def _update_status(self) -> None:
            if not self._document or not self._document.tool_poses:
                self._status.setText("No toolpath")
                return
            poses = self._document.tool_poses
            index = max(0, min(self._play_index, len(poses) - 1))
            pose = poses[index]
            self._status.setText(
                "Block %d/%d  %s  XYZ(%.2f,%.2f,%.2f)  B%.2f C%.2f"
                % (
                    index + 1,
                    len(poses),
                    pose.motion.value.upper(),
                    pose.machine_xyz_radius[0],
                    pose.machine_xyz_radius[1],
                    pose.machine_xyz_radius[2],
                    pose.b_deg,
                    pose.c_deg,
                )
            )

        def _push_pose(self) -> None:
            if not self._document or not self._document.tool_poses:
                return
            poses = self._document.tool_poses
            index = max(0, min(self._play_index, len(poses) - 1))
            self._update_status()
            self.playIndexChanged.emit(index)
            if self._page_loaded:
                self._view.page().runJavaScript(
                    "window.setPoseIndex(%d)" % index
                )

else:
    class WebPreviewWidget(QWidget):
        playIndexChanged = Signal(int)

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setMinimumSize(560, 480)
            self._document: Optional[PreviewDocument] = None
            self._tool: Optional[PreviewToolGeometry] = None
            self._stl_path: Optional[str] = None
            self._play_index = 0
            label = QLabel(
                "3D web preview requires PySide6.QtWebEngineWidgets.\n"
                "Install PySide6-WebEngine or run outside the FreeCAD environment.",
                self,
            )
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color:#9aa4ad;font-size:14pt;padding:40px;")
            from PySide6.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(self)
            layout.addWidget(label)

        def set_document(self, document):
            self._document = document

        def set_tool(self, kind, diameter, stickout,
                     cutting_length=0.0, included_angle_deg=None, tip_flat_diameter=0.0):
            pass

        def set_workpiece_stl(self, path):
            self._stl_path = path

        def play(self):
            pass

        def pause(self):
            pass

        def reset(self):
            pass
