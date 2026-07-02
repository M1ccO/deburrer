#!/usr/bin/env python3
import sys
import os
import json
from dataclasses import dataclass, asdict

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QLineEdit, QGridLayout, QStackedWidget,
    QFileDialog, QCheckBox, QComboBox, QMessageBox, QFrame, QListWidget,
    QListWidgetItem, QSizePolicy, QListView
)
from PySide2.QtCore import Qt, QUrl
from PySide2.QtGui import QDesktopServices

# Try WebEngine, but allow running without it
try:
    from PySide2.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False

import deburr_tool  # your existing logic

# --- DEBUG INFO (put it here, AFTER HAS_WEBENGINE is defined) ---
print("NTX UI launched with:", sys.executable)
print("HAS_WEBENGINE =", HAS_WEBENGINE)
# ---------------------------------------------------------------


# -----------------------------------------------------------
# Embedded HTML viewer for GUIDANCE (3D toolpath preview)
# -----------------------------------------------------------

GCODE_VIEWER_HTML = r"""<!DOCTYPE html>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NTX Deburr – 3D Viewer</title>
<style>
  body {
    margin: 0;
    /* Match the Path & Geometry page background (light grey) */
    background: #f4f4f4;
    color: #333333;
    font-family: Arial, sans-serif;
  }
  #controls {
    padding: 8px;
  }
  #viewer {
    width: 100vw;
    height: calc(100vh - 200px);
    /* Light background to blend with the surrounding UI */
    background: #ffffff;
  }
  canvas { display: block; }
  button, input, select {
    margin-right: 4px;
    vertical-align: middle;
    padding: 3px 6px;
    font-size: 11px;
  }
  label { margin-right: 8px; }

  /* Hide the G-code text area when embedded guidance is used */
  #gcodeInput {
    display: none;
    height: 0;
    padding: 0;
    margin: 0;
  }
</style>
</head>
<body>
<div id="controls">
  <button id="renderBtn">Render 3D</button>
  <button id="playBtn">Play</button>
  <button id="stopBtn" disabled>Stop</button>
  <button id="togglePoints">Hide points</button>
  <label>Line width: <input id="lineWidthSlider" type="range" min="1" max="10" value="2"></label>
  <label>BG: <input id="bgColorPicker" type="color" value="#111111"></label>
  <label>Grid: <input id="gridCheckbox" type="checkbox"></label>
  <!-- Removed Z scale and tool controls -->
  <button id="toggleOriginal">Show original</button>
  <br/>
  <!-- View selection dropdown -->
  <label>View: 
    <select id="viewSelect">
      <option value="iso">Iso</option>
      <option value="top">Top</option>
      <option value="bottom">Bottom</option>
      <option value="front">Front</option>
      <option value="back">Back</option>
      <option value="left">Left</option>
      <option value="right">Right</option>
    </select>
  </label>
  <textarea id="gcodeInput" style="width: 100%; height: 100px; margin-top: 8px;"></textarea>
  <div style="font-size:12px;color:#bbb;margin-top:6px;">
    Left-drag = Rotate · Middle-drag = Pan · Shift+Left = Pan · Ctrl+Left = Zoom · Wheel = Zoom
  </div>
</div>
<div id="viewer"><canvas id="canvas"></canvas></div>
<script>
// state variables
let canvas = document.getElementById("canvas");
let viewer = document.getElementById("viewer");
let ctx;
let target = { x:0, y:0, z:0 };
let camDist = 150;
let yaw = -Math.PI*0.75;
let pitch = -0.6;
let dragging = false;
let dragMode = "rotate";
let lastX = 0, lastY = 0;
let deburrRaw = [];
let originalRaw = [];
let points3D = [];
let original3D = [];
let showPoints = true;
let lineWidth = 2;
let backgroundColor = "#111111";
let showGrid = false;
// removed zScale and toolModel
let showOriginalPath = false;
let playing = false;
let playIdx = 0;
let playInterval = null;

// parse gcode and extract optional JSON arrays
function parseGCodeText(text) {
  deburrRaw = [];
  originalRaw = [];
  const lines = text.split(/\r?\n/);
  for (let ln of lines) {
    let trimmed = ln.trim();
    if (trimmed.startsWith(";ORIGINAL_POINTS:")) {
      try {
        let jsonStr = trimmed.substring(trimmed.indexOf(":") + 1).trim();
        originalRaw = JSON.parse(jsonStr);
      } catch(e) {}
    } else if (trimmed.startsWith(";DEBURR_POINTS:")) {
      try {
        let jsonStr = trimmed.substring(trimmed.indexOf(":") + 1).trim();
        deburrRaw = JSON.parse(jsonStr);
      } catch(e) {}
    }
  }
  if (deburrRaw.length === 0) {
    let x=0,y=0,z=0;
    for (let raw of lines) {
      let line = raw.split(/[;(]/)[0].trim();
      if (!line) continue;
      let mX = line.match(/X(-?\d+\.?\d*)/i);
      let mY = line.match(/Y(-?\d+\.?\d*)/i);
      let mZ = line.match(/Z(-?\d+\.?\d*)/i);
      if (mX) x = parseFloat(mX[1]);
      if (mY) y = parseFloat(mY[1]);
      if (mZ) z = parseFloat(mZ[1]);
      if (mX || mY || mZ) deburrRaw.push([x,y,z]);
    }
  }
}

function normalizePoints() {
  points3D = [];
  original3D = [];
  if (deburrRaw.length === 0 && originalRaw.length === 0) return;
  let xs = [], ys = [], zs = [];
  for (let p of deburrRaw) {
    xs.push(p[0]); ys.push(p[1]); zs.push(p[2]);
  }
  for (let p of originalRaw) {
    xs.push(p[0]); ys.push(p[1]); zs.push(p[2]);
  }
  let minX = Math.min(...xs), maxX = Math.max(...xs);
  let minY = Math.min(...ys), maxY = Math.max(...ys);
  let minZ = Math.min(...zs), maxZ = Math.max(...zs);
  let cx = (minX + maxX) / 2;
  let cy = (minY + maxY) / 2;
  let cz = (minZ + maxZ) / 2;
  target = { x: cx, y: cy, z: cz };
  let size = Math.max(maxX - minX, maxY - minY, maxZ - minZ);
  if (size === 0) size = 1;
  let scale = 100 / size;
  for (let p of deburrRaw) {
    points3D.push({ x:(p[0]-cx)*scale, y:(p[1]-cy)*scale, z:(p[2]-cz)*scale });
  }
  for (let p of originalRaw) {
    original3D.push({ x:(p[0]-cx)*scale, y:(p[1]-cy)*scale, z:(p[2]-cz)*scale });
  }
}

// Compute camera distance so that the current geometry fits comfortably within the viewport.
function fitToWindow() {
  // Determine the maximum absolute coordinate across all normalized points
  let maxCoord = 0;
  for (const p of points3D) {
    maxCoord = Math.max(maxCoord, Math.abs(p.x), Math.abs(p.y), Math.abs(p.z));
  }
  for (const p of original3D) {
    maxCoord = Math.max(maxCoord, Math.abs(p.x), Math.abs(p.y), Math.abs(p.z));
  }
  if (maxCoord > 0) {
    // Set camera distance based on the bounding radius. Multiplier tuned for a good fit.
    camDist = Math.max(10, maxCoord * 3.5);
  }
}

function project(pt) {
  const cosy = Math.cos(yaw), siny = Math.sin(yaw);
  const cosp = Math.cos(pitch), sinp = Math.sin(pitch);
  let dx = pt.x;
  let dy = pt.y;
  let dz = pt.z;
  const x1 = dx * cosy + dz * siny;
  const z1 = -dx * siny + dz * cosy;
  const y2 = dy * cosp - z1 * sinp;
  const k = 200 / camDist;
  return {
    x: canvas.width/2 + x1 * k,
    y: canvas.height/2 - y2 * k
  };
}

function drawGrid() {
  let maxCoord = 0;
  for (let p of points3D) {
    maxCoord = Math.max(maxCoord, Math.abs(p.x), Math.abs(p.y));
  }
  for (let p of original3D) {
    maxCoord = Math.max(maxCoord, Math.abs(p.x), Math.abs(p.y));
  }
  if (maxCoord === 0) return;
  let size = Math.ceil(maxCoord/20)*20;
  let spacing = size/5;
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#333333";
  for (let gx = -size; gx <= size; gx += spacing) {
    let p0 = project({x: gx, y: -size, z: 0});
    let p1 = project({x: gx, y: size, z: 0});
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
  }
  for (let gy = -size; gy <= size; gy += spacing) {
    let p0 = project({x: -size, y: gy, z: 0});
    let p1 = project({x: size, y: gy, z: 0});
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.stroke();
  }
}

// drawTool removed as tool model functionality is no longer needed

function draw() {
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = backgroundColor;
  ctx.fillRect(0,0,canvas.width,canvas.height);
  if (showGrid) {
    drawGrid();
  }
  let AX = 40;
  let o = project({x:0,y:0,z:0});
  let xp = project({x:AX,y:0,z:0});
  let yp = project({x:0,y:AX,z:0});
  let zp = project({x:0,y:0,z:AX});
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#ff4444";
  ctx.beginPath(); ctx.moveTo(o.x,o.y); ctx.lineTo(xp.x,xp.y); ctx.stroke();
  ctx.strokeStyle = "#44ff44";
  ctx.beginPath(); ctx.moveTo(o.x,o.y); ctx.lineTo(yp.x,yp.y); ctx.stroke();
  ctx.strokeStyle = "#4444ff";
  ctx.beginPath(); ctx.moveTo(o.x,o.y); ctx.lineTo(zp.x,zp.y); ctx.stroke();
  if (points3D.length > 1) {
    ctx.lineWidth = lineWidth;
    ctx.strokeStyle = "#00e5ff";
    ctx.beginPath();
    let start = project(points3D[0]);
    ctx.moveTo(start.x,start.y);
    let maxIdx = playing ? playIdx : points3D.length-1;
    for (let i=1; i<=maxIdx; i++) {
      let p = project(points3D[i]);
      ctx.lineTo(p.x,p.y);
    }
    ctx.stroke();
    if (showPoints) {
      ctx.fillStyle = "#ffcc00";
      let drawCount = playing ? playIdx+1 : points3D.length;
      for (let i=0; i<drawCount; i++) {
        let pt = project(points3D[i]);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 3, 0, Math.PI*2);
        ctx.fill();
      }
    }
  }
  if (showOriginalPath && original3D.length > 1) {
    ctx.lineWidth = lineWidth;
    ctx.strokeStyle = "#ff00ff";
    ctx.beginPath();
    let start = project(original3D[0]);
    ctx.moveTo(start.x,start.y);
    let maxO = playing ? Math.min(playIdx, original3D.length-1) : original3D.length-1;
    for (let i=1; i<=maxO; i++) {
      let p = project(original3D[i]);
      ctx.lineTo(p.x,p.y);
    }
    ctx.stroke();
    if (showPoints) {
      ctx.fillStyle = "#ff66ff";
      let drawCount = playing ? Math.min(playIdx+1, original3D.length) : original3D.length;
      for (let i=0; i<drawCount; i++) {
        let pt = project(original3D[i]);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 3, 0, Math.PI*2);
        ctx.fill();
      }
    }
  }
  // removed call to drawTool()
}

document.getElementById("renderBtn").onclick = () => {
  let txt = document.getElementById("gcodeInput").value || "";
  parseGCodeText(txt);
  normalizePoints();
  // Adjust camera to fit the geometry in view
  fitToWindow();
  // Reset camera orientation to isometric
  yaw = -Math.PI*0.75;
  pitch = -0.6;
  stopPlayback();
  draw();
};
document.getElementById("playBtn").onclick = () => {
  if (playing || points3D.length < 2) return;
  playing = true;
  playIdx = 0;
  document.getElementById("playBtn").disabled = true;
  document.getElementById("stopBtn").disabled = false;
  playInterval = setInterval(() => {
    playIdx++;
    if (playIdx >= points3D.length) {
      stopPlayback();
      return;
    }
    draw();
  }, 50);
};
function stopPlayback() {
  if (!playing) return;
  playing = false;
  if (playInterval) { clearInterval(playInterval); playInterval = null; }
  document.getElementById("playBtn").disabled = false;
  document.getElementById("stopBtn").disabled = true;
  playIdx = points3D.length-1;
  draw();
}
document.getElementById("stopBtn").onclick = stopPlayback;
document.getElementById("togglePoints").onclick = () => {
  showPoints = !showPoints;
  document.getElementById("togglePoints").textContent = showPoints ? "Hide points" : "Show points";
  draw();
};
document.getElementById("lineWidthSlider").oninput = (e) => {
  lineWidth = parseFloat(e.target.value);
  draw();
};
document.getElementById("bgColorPicker").oninput = (e) => {
  backgroundColor = e.target.value;
  draw();
};
document.getElementById("gridCheckbox").onchange = (e) => {
  showGrid = e.target.checked;
  draw();
};
// removed zScale and toolModel event handlers
document.getElementById("toggleOriginal").onclick = () => {
  showOriginalPath = !showOriginalPath;
  document.getElementById("toggleOriginal").textContent = showOriginalPath ? "Hide original" : "Show original";
  draw();
};
// Dropdown view selection handler
document.getElementById("viewSelect").onchange = (e) => {
  const v = e.target.value;
  if (v === "top")    { yaw = 0; pitch = -Math.PI/2; }
  if (v === "bottom") { yaw = 0; pitch =  Math.PI/2; }
  if (v === "front")  { yaw = 0; pitch = 0; }
  if (v === "back")   { yaw = Math.PI; pitch = 0; }
  if (v === "left")   { yaw = -Math.PI/2; pitch = 0; }
  if (v === "right")  { yaw =  Math.PI/2; pitch = 0; }
  if (v === "iso")    { yaw = -Math.PI*0.75; pitch = -0.6; }
  draw();
};

// Update geometry without resetting camera
window.updateGCode = function(text) {
  const txt = text || "";
  document.getElementById("gcodeInput").value = txt;
  parseGCodeText(txt);
  normalizePoints();
  // Do not call fitToWindow or reset yaw/pitch; preserve current view
  stopPlayback();
  draw();
};
window.setGCode = function(text) {
  document.getElementById("gcodeInput").value = text || "";
  document.getElementById("renderBtn").click();
};
function initViewer() {
  canvas.width = viewer.clientWidth;
  canvas.height = viewer.clientHeight;
  ctx = canvas.getContext("2d");
  window.addEventListener("resize", () => {
    canvas.width = viewer.clientWidth;
    canvas.height = viewer.clientHeight;
    draw();
  });
  canvas.addEventListener("mousedown", e => {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    if (e.button === 1) dragMode = "pan";
    else if (e.shiftKey) dragMode = "pan";
    else if (e.ctrlKey) dragMode = "zoom";
    else dragMode = "rotate";
  });
  window.addEventListener("mouseup", () => { dragging = false; });
  window.addEventListener("mousemove", e => {
    if (!dragging) return;
    let dx = e.clientX - lastX;
    let dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    if (dragMode === "rotate") {
      yaw += dx * 0.01;
      pitch += dy * 0.01;
      let limit = Math.PI/2 * 0.99;
      if (pitch > limit) pitch = limit;
      if (pitch < -limit) pitch = -limit;
    } else if (dragMode === "pan") {
      let f = camDist * 0.005;
      let right = { x: Math.cos(yaw), y: 0, z: -Math.sin(yaw) };
      let up = { x: 0, y: 1, z: 0 };
      target.x -= right.x * dx * f;
      target.y += up.y * dy * f;
      target.z -= right.z * dx * f;
    } else if (dragMode === "zoom") {
      camDist *= (1 - dy * 0.01);
      camDist = Math.max(5, Math.min(camDist, 1000));
    }
    draw();
  });
  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    camDist *= (1 + e.deltaY * 0.001);
    camDist = Math.max(5, Math.min(camDist, 1000));
    draw();
  }, { passive: false });
}
initViewer();
</script>
</body>
</html>
"""


# -----------------------------------------------------------
# Settings / state models
# -----------------------------------------------------------

SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"),
    ".ntx_deburr_settings.json"
)


@dataclass
class FileState:
    csv_path: str = ""


@dataclass
class TransformState:
    model_scale: float = 1.0
    model_offset_x: float = 0.0
    model_offset_y: float = 0.0
    model_offset_z: float = 0.0

    radial_scale: float = 1.0
    clearance_z: float = 3.0


@dataclass
class MachineState:
    program_number: int = 9001
    tool_number: int = 5
    b_angle: float = 45.0

    feedrate: float = 800.0
    spindle_speed: float = 6000.0
    spindle_dir: str = "CW"

    coolant_on: bool = True
    cutter_comp: str = "NONE"

    spindle_side: str = "MAIN"

    output_folder: str = os.path.join(
        os.path.expanduser("~"),
        "Desktop",
        "NTX_Deburr"
    )


@dataclass
class DeburrState:
    file: FileState
    transform: TransformState
    machine: MachineState

    @staticmethod
    def default():
        return DeburrState(FileState(), TransformState(), MachineState())


def load_settings():
    if not os.path.isfile(SETTINGS_PATH):
        return DeburrState.default()

    try:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return DeburrState.default()

    file_data = data.get("file", {})
    tr_data = data.get("transform", {})
    mc_data = data.get("machine", {})

    return DeburrState(
        file=FileState(
            csv_path=file_data.get("csv_path", "")
        ),
        transform=TransformState(
            model_scale=tr_data.get("model_scale", 1.0),
            model_offset_x=tr_data.get("model_offset_x", 0.0),
            model_offset_y=tr_data.get("model_offset_y", 0.0),
            model_offset_z=tr_data.get("model_offset_z", 0.0),
            radial_scale=tr_data.get("radial_scale", 1.0),
            clearance_z=tr_data.get("clearance_z", 3.0),
        ),
        machine=MachineState(
            program_number=mc_data.get("program_number", 9001),
            tool_number=mc_data.get("tool_number", 5),
            b_angle=mc_data.get("b_angle", 45.0),
            feedrate=mc_data.get("feedrate", 800.0),
            spindle_speed=mc_data.get("spindle_speed", 6000.0),
            spindle_dir=mc_data.get("spindle_dir", "CW"),
            coolant_on=mc_data.get("coolant_on", True),
            cutter_comp=mc_data.get("cutter_comp", "NONE"),
            spindle_side=mc_data.get("spindle_side", "MAIN"),
            output_folder=mc_data.get(
                "output_folder",
                MachineState().output_folder
            ),
        ),
    )


def save_settings(state):
    data = {
        "file": asdict(state.file),
        "transform": asdict(state.transform),
        "machine": asdict(state.machine),
    }
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Failed to save settings:", e)



# -----------------------------------------------------------
# Guidance overlay – uses WebEngine if available
# -----------------------------------------------------------

class GuidanceOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 140);")
        self.setVisible(False)

        self._html_loaded = False
        self._pending_gcode = None
        self._last_gcode = ""
        self._can_embed = HAS_WEBENGINE and QWebEngineView is not None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet(
            "background-color: #202020; border: 1px solid #777;"
        )
        container.setMinimumSize(1000, 800)

        v = QVBoxLayout(container)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("3D Guidance – Toolpath Preview")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.setStyleSheet(
            "color: #ffffff;"
            "background-color: #404040;"
            "border: 1px solid #888;"
            "padding: 2px 8px;"
        )
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)


        v.addLayout(header)

        if self._can_embed:
            # Normal in-app WebEngine viewer
            self.web = QWebEngineView()
            v.addWidget(self.web, stretch=1)
            self.web.setHtml(GCODE_VIEWER_HTML)
            self.web.loadFinished.connect(self._on_load_finished)
        else:
            # Fallback: no WebEngine in this Python (FreeCAD case)
            self.web = None

            info = QLabel(
                "QtWebEngine is not available in this Python environment.\n\n"
                "The GUIDANCE 3D preview cannot be embedded in FreeCAD.\n"
                "You can still open the preview in your web browser."
            )
            info.setStyleSheet("color: #ffffff;")
            info.setAlignment(Qt.AlignCenter)

            button_row = QHBoxLayout()
            button_row.addStretch()
            open_btn = QPushButton("Open in Browser")
            open_btn.setFixedWidth(130)
            open_btn.clicked.connect(self._open_in_browser)
            button_row.addWidget(open_btn)
            button_row.addStretch()

            v.addWidget(info, stretch=1)
            v.addLayout(button_row)

        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(container)
        center_layout.addStretch()

        outer.addStretch()
        outer.addLayout(center_layout)
        outer.addStretch()

    def _on_load_finished(self, ok):
        self._html_loaded = ok
        if ok and self._pending_gcode is not None:
            self.set_gcode(self._pending_gcode)
            self._pending_gcode = None

    def set_gcode(self, gcode_text: str):
        # Always remember the last NC text (for browser fallback)
        self._last_gcode = gcode_text or ""

        if not self._can_embed or self.web is None:
            # In FreeCAD we just keep it for _open_in_browser()
            return

        if not self._html_loaded:
            self._pending_gcode = self._last_gcode
            return

        js = "window.setGCode(%s);" % json.dumps(self._last_gcode)
        self.web.page().runJavaScript(js)

    def _open_in_browser(self):
        """Fallback for FreeCAD: open guidance viewer HTML in default browser,
        and put NC text on the clipboard so you can paste it."""
        if not self._last_gcode:
            return

        # Write HTML to a temporary file
        import tempfile
        fd, path = tempfile.mkstemp(
            prefix="ntx_deburr_guidance_", suffix=".html"
        )
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(GCODE_VIEWER_HTML)

        # Copy NC text to clipboard for easy paste
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(self._last_gcode)

        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def resizeEvent(self, event):
        super().resizeEvent(event)



# -----------------------------------------------------------
# Main window
# -----------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, csv_override=None):
        super().__init__()

        self.setWindowTitle("NTX DEBURR TOOL – v1.0")
        self.resize(1200, 700)

        self.state = load_settings()
        if csv_override:
            self.state.file.csv_path = csv_override

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        self.nav_list = self._create_nav_list()
        self.content_frame, self.stack = self._create_content_stack()

        top_layout.addWidget(self.nav_list)
        top_layout.addWidget(self.content_frame, stretch=1)

        bottom_bar = self._create_bottom_bar()

        root_layout.addWidget(top, stretch=1)
        root_layout.addWidget(bottom_bar, stretch=0)

        self.guidance_overlay = GuidanceOverlay(self.centralWidget())
        self.guidance_overlay.resize(self.centralWidget().size())

        # State flags for embedded guidance preview
        self.guidance_open = False
        self.guidance_html_loaded = False
        self.pending_guidance_gcode = None
        self.last_nc_text = ""

        self._populate_fields_from_state()
        self.nav_list.setCurrentRow(0)

    # -----------------------------
    # Navigation & pages
    # -----------------------------
    def _create_nav_list(self):
        nav = QListWidget()
        nav.setFixedWidth(220)
        nav.setStyleSheet(
            "QListWidget { background-color: white; border: 1px solid #c0c0c0; }"
            "QListWidget::item { height: 40px; padding-left: 8px; }"
            "QListWidget::item:selected { background-color: #4aa3ff; color: white; }"
        )

        for name in ["Path & Geometry", "Offsets & Scaling",
                     "Machine Setup", "NC Output"]:
            item = QListWidgetItem(name)
            nav.addItem(item)

        nav.currentRowChanged.connect(self._switch_tab)
        return nav

    def _create_content_stack(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: transparent; border: none; }")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.stack = QStackedWidget()

        page1 = self._create_page_path_geometry()
        page2 = self._create_page_offsets_scaling()
        page3 = self._create_page_machine_setup()
        page4 = self._create_page_nc_output()

        self.stack.addWidget(page1)
        self.stack.addWidget(page2)
        self.stack.addWidget(page3)
        self.stack.addWidget(page4)

        layout.addWidget(self.stack)
        return frame, self.stack

    def _create_two_column_page(self, title_text):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        title = QLabel(title_text)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        outer.addWidget(title)

        main_area = QWidget()
        h = QHBoxLayout(main_area)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        fields_widget = QWidget()
        grid = QGridLayout(fields_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        diagram = QFrame()
        diagram.setMinimumWidth(220)
        diagram.setStyleSheet("background-color: #f4f4f4; border: 1px solid #cccccc;")
        diag_layout = QVBoxLayout(diagram)
        diag_layout.setContentsMargins(8, 8, 8, 8)
        diag_label = QLabel("Diagram / Preview\n(placeholder)")
        diag_label.setAlignment(Qt.AlignCenter)
        diag_layout.addWidget(diag_label, alignment=Qt.AlignCenter)

        h.addWidget(fields_widget, stretch=1)
        h.addWidget(diagram, stretch=0)

        outer.addWidget(main_area, stretch=1)
        # Attach references so page can access fields_widget and diagram later
        root.fields_widget = fields_widget
        root.diagram = diagram
        return root, grid

    def _styled_lineedit(self):
        edit = QLineEdit()
        edit.setMinimumWidth(110)
        edit.setMinimumHeight(30)
        edit.setStyleSheet("""
            QLineEdit {
                font-size: 10pt;
                font-family: 'Segoe UI';
                font-weight: 100;
                background-color: #ffffff;
                border: 1px solid #c8c8c8;
                padding: 2px 4px;
                border-radius: 2px;
            }
            QLineEdit:focus {
                border: 1px solid #4a90e2;
                background-color: #ffffff;
            }
        """)
        return edit

    def _field_block(self, title, widget):
        cont = QWidget()
        cont.setStyleSheet("background: transparent;")
        cont.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        label = QLabel(title)
        label.setStyleSheet("font-size: 10pt;")
        v.addWidget(label)
        v.addWidget(widget)

        return cont

    def _style_combobox_popup(self, combo):
        view = QListView()
        view.setStyleSheet("""
            QListView {
                background-color: #f7f7f7;
                color: #000000;
                selection-background-color: #4a90e2;
                selection-color: #ffffff;
                border: 1px solid #c8c8c8;
            }
        """)
        combo.setView(view)

    # -----------------------------
    # Individual pages
    # -----------------------------
    def _create_page_path_geometry(self):
        page, grid = self._create_two_column_page("Path & Geometry")

        row = 0
        self.csv_path_edit = self._styled_lineedit()
        self.csv_path_edit.setReadOnly(True)
        self.csv_path_edit.setMinimumWidth(300)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_csv)
        reload_btn = QPushButton("Reload CSV")
        reload_btn.clicked.connect(self._reload_csv)

        # Create and store the input path label and buttons so they can be hidden when guidance is open
        self.path_input_label = QLabel("Input Path:")
        self.path_browse_btn = browse_btn
        self.path_reload_btn = reload_btn

        grid.addWidget(self.path_input_label, row, 0)
        grid.addWidget(self.csv_path_edit, row, 1, 1, 2)
        row += 1

        grid.addWidget(self.path_browse_btn, row, 1)
        grid.addWidget(self.path_reload_btn, row, 2)
        row += 1

        row += 1

        self.model_scale_edit = self._styled_lineedit()
        self.offset_x_edit = self._styled_lineedit()
        self.offset_y_edit = self._styled_lineedit()
        self.offset_z_edit = self._styled_lineedit()

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        row_layout.addWidget(self._field_block("Model Scale", self.model_scale_edit))
        row_layout.addWidget(self._field_block("Offset X", self.offset_x_edit))
        row_layout.addWidget(self._field_block("Offset Y", self.offset_y_edit))
        row_layout.addWidget(self._field_block("Offset Z", self.offset_z_edit))
        row_layout.addStretch()

        grid.addWidget(row_widget, row, 0, 1, 3)

        # Save row index and row widget for relocation when guidance is toggled
        self.path_row_index = row
        self.path_row_widget = row_widget
        # Save references to grid and page's fields widget and diagram
        self.path_grid = grid
        # _create_two_column_page attaches fields_widget and diagram as attributes on the page
        self.path_fields_widget = getattr(page, 'fields_widget', None)
        self.path_diagram = getattr(page, 'diagram', None)

        # Connect live-update signals for scale and offsets
        self.model_scale_edit.textChanged.connect(self._on_transform_changed)
        self.offset_x_edit.textChanged.connect(self._on_transform_changed)
        self.offset_y_edit.textChanged.connect(self._on_transform_changed)
        self.offset_z_edit.textChanged.connect(self._on_transform_changed)

        # Set up embedded guidance container (initially hidden)
        self.path_guidance_container = QWidget()
        self.path_guidance_container.setVisible(False)
        gc_layout = QVBoxLayout(self.path_guidance_container)
        gc_layout.setContentsMargins(0, 0, 0, 0)
        gc_layout.setSpacing(4)

        # Create web viewer for guidance if WebEngine is available
        if HAS_WEBENGINE and QWebEngineView is not None:
            self.path_guidance_viewer = QWebEngineView()
            self.path_guidance_viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            gc_layout.addWidget(self.path_guidance_viewer, stretch=1)
            # Connect loadFinished signal to apply pending NC text
            self.path_guidance_viewer.loadFinished.connect(self._on_guidance_html_loaded)
        else:
            self.path_guidance_viewer = None

        # Bottom container for moving the scale/offset row widget when guidance is visible
        self.path_guidance_bottom = QWidget()
        bottom_layout = QHBoxLayout(self.path_guidance_bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        gc_layout.addWidget(self.path_guidance_bottom, stretch=0)

        # Insert guidance container at the beginning of the main area layout
        # The main area is the parent of fields_widget
        if self.path_fields_widget is not None:
            main_area = self.path_fields_widget.parentWidget()
            if main_area is not None:
                layout = main_area.layout()
                if layout is not None:
                    layout.insertWidget(0, self.path_guidance_container, stretch=1)

        return page

    def _create_page_offsets_scaling(self):
        page, grid = self._create_two_column_page("Offsets & Scaling")

        row = 0
        self.radial_scale_edit = self._styled_lineedit()
        self.clearance_edit = self._styled_lineedit()

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        row_layout.addWidget(self._field_block("Radial Scale (Y/Z)", self.radial_scale_edit))
        row_layout.addWidget(self._field_block("Z Clearance", self.clearance_edit))
        row_layout.addStretch()

        grid.addWidget(row_widget, row, 0, 1, 3)
        # Connect live-update for radial scale when guidance is open
        self.radial_scale_edit.textChanged.connect(self._on_transform_changed)

        return page

    # ---------------------------------------------
    # Guidance HTML callbacks and live update
    # ---------------------------------------------
    def _on_guidance_html_loaded(self, ok):
        """
        Callback when the embedded guidance viewer HTML has loaded.
        If there is pending NC text waiting, send it to the viewer.
        """
        self.guidance_html_loaded = ok
        if ok and self.pending_guidance_gcode:
            # Send pending gcode to viewer using setGCode (initial load)
            self._send_guidance_gcode(self.pending_guidance_gcode, update=False)
            self.pending_guidance_gcode = None

    def _send_guidance_gcode(self, gcode_text: str, update: bool = False):
        """
        Send the NC text to the embedded guidance viewer.
        If update is True, use updateGCode (preserves camera orientation);
        otherwise use setGCode (resets orientation and fits geometry).
        """
        if not self.path_guidance_viewer or not self.guidance_html_loaded:
            # If HTML hasn't loaded yet, store for later
            self.pending_guidance_gcode = gcode_text
            return
        # Construct JS call; text must be JSON-stringified
        method = 'updateGCode' if update else 'setGCode'
        js = f"window.{method}({json.dumps(gcode_text)})"
        self.path_guidance_viewer.page().runJavaScript(js)

    def _on_transform_changed(self):
        """
        Called when model scale or offsets or radial scale fields change.
        If guidance is open and viewer loaded, update the preview without resetting the view.
        """
        if not self.guidance_open or not self.guidance_html_loaded:
            return
        # Update numeric values in state quietly (don't show warnings)
        try:
            self.state.transform.model_scale = float(self.model_scale_edit.text())
            self.state.transform.model_offset_x = float(self.offset_x_edit.text())
            self.state.transform.model_offset_y = float(self.offset_y_edit.text())
            self.state.transform.model_offset_z = float(self.offset_z_edit.text())
            self.state.transform.radial_scale = float(self.radial_scale_edit.text())
            self.state.transform.clearance_z = float(self.clearance_edit.text())
        except ValueError:
            return
        # Build preview NC text and update viewer
        nc_text = self._build_guidance_nc_text()
        if nc_text:
            self._send_guidance_gcode(nc_text, update=True)

    # ---------------------------------------------
    # NC preview dialog
    # ---------------------------------------------
    def _preview_nc(self):
        """
        Show a modal dialog with the NC text that would be generated.
        Uses the same logic as guidance preview but without geometry comments.
        """
        if not self._update_state_from_fields():
            return
        nc_text = self._build_preview_nc_text()
        if not nc_text:
            return
        from PySide2.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle("NC Preview")
        dlg.resize(800, 600)
        v = QVBoxLayout(dlg)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(nc_text)
        v.addWidget(text_edit, stretch=1)
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn, alignment=Qt.AlignRight)
        dlg.exec_()

    def _create_page_machine_setup(self):
        page, grid = self._create_two_column_page("Machine Setup")

        row = 0
        self.program_number_edit = self._styled_lineedit()
        self.tool_number_edit = self._styled_lineedit()
        self.b_angle_edit = self._styled_lineedit()

        row1 = QWidget()
        row1_l = QHBoxLayout(row1)
        row1_l.setContentsMargins(0, 0, 0, 0)
        row1_l.setSpacing(12)
        row1_l.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        row1_l.addWidget(self._field_block("Program Number", self.program_number_edit))
        row1_l.addWidget(self._field_block("Tool Number", self.tool_number_edit))
        row1_l.addWidget(self._field_block("B-axis Angle", self.b_angle_edit))
        row1_l.addStretch()

        grid.addWidget(row1, row, 0, 1, 3)
        row += 1

        self.spindle_side_combo = QComboBox()
        self.spindle_side_combo.addItems(["Main spindle (M303, G54)", "Subspindle (M304, G57)"])
        self._style_combobox_popup(self.spindle_side_combo)

        row1b = QWidget()
        row1b_l = QHBoxLayout(row1b)
        row1b_l.setContentsMargins(0, 0, 0, 0)
        row1b_l.setSpacing(12)
        row1b_l.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        row1b_l.addWidget(self._field_block("Spindle / Offset", self.spindle_side_combo))
        row1b_l.addStretch()

        grid.addWidget(row1b, row, 0, 1, 3)
        row += 1

        self.feedrate_edit = self._styled_lineedit()
        self.spindle_speed_edit = self._styled_lineedit()

        row2 = QWidget()
        row2_l = QHBoxLayout(row2)
        row2_l.setContentsMargins(0, 0, 0, 0)
        row2_l.setSpacing(12)
        row2_l.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        row2_l.addWidget(self._field_block("Feedrate (F)", self.feedrate_edit))
        row2_l.addWidget(self._field_block("Spindle Speed (RPM)", self.spindle_speed_edit))
        row2_l.addStretch()

        grid.addWidget(row2, row, 0, 1, 3)
        row += 1

        self.spindle_dir_combo = QComboBox()
        self.spindle_dir_combo.addItems(["CW", "CCW"])
        self.spindle_dir_combo.setMinimumHeight(30)

        self.coolant_checkbox = QCheckBox("Coolant ON")

        self.cutter_comp_combo = QComboBox()
        self.cutter_comp_combo.addItems(["NONE", "G41", "G42"])
        self.cutter_comp_combo.setMinimumHeight(30)

        self._style_combobox_popup(self.spindle_dir_combo)
        self._style_combobox_popup(self.cutter_comp_combo)

        row3 = QWidget()
        row3_l = QHBoxLayout(row3)
        row3_l.setContentsMargins(0, 0, 0, 0)
        row3_l.setSpacing(12)
        row3_l.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        row3_l.addWidget(self._field_block("Spindle Direction", self.spindle_dir_combo))
        row3_l.addWidget(self._field_block("Coolant", self.coolant_checkbox))
        row3_l.addWidget(self._field_block("Cutter Comp", self.cutter_comp_combo))
        row3_l.addStretch()

        grid.addWidget(row3, row, 0, 1, 3)

        return page

    def _create_page_nc_output(self):
        page, grid = self._create_two_column_page("NC Output")

        row = 0
        self.output_folder_edit = self._styled_lineedit()
        self.output_folder_edit.setMinimumWidth(260)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_output_folder)

        grid.addWidget(QLabel("Output Folder:"), row, 0)
        grid.addWidget(self.output_folder_edit, row, 1)
        grid.addWidget(browse_btn, row, 2)
        row += 1

        self.program_file_label = QLabel("(will be Oxxxx_deburr.nc)")
        grid.addWidget(QLabel("Program File:"), row, 0)
        grid.addWidget(self.program_file_label, row, 1, 1, 2)
        row += 1

        # Remove page-level preview button; preview is handled by the bottom bar
        pass  # placeholder: NC preview is triggered from bottom bar

        return page

    # -----------------------------
    # Bottom bar / buttons
    # -----------------------------
    def _create_bottom_bar(self):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        self.guidance_btn = QPushButton("GUIDANCE")
        self.guidance_btn.setMinimumHeight(40)
        self.guidance_btn.setStyleSheet(
            "QPushButton {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #f3f3f3, stop:1 #e0e0e0);"
            "border: 1px solid #b8b8b8;"
            "padding: 6px 20px;"
            "color: #444444;"
            "font-weight: normal;"
            "font-size: 11pt;"
            "}"
            "QPushButton:hover {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #ffffff, stop:1 #e8e8e8);"
            "}"
            "QPushButton:pressed {"
            "background-color: #d0d0d0;"
            "}"
        )
        self.guidance_btn.clicked.connect(self._toggle_guidance)

        # Preview NC button – shows NC text in a modal dialog
        self.preview_nc_btn = QPushButton("PREVIEW NC")
        self.preview_nc_btn.setMinimumHeight(40)
        self.preview_nc_btn.setStyleSheet(
            "QPushButton {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #f3f3f3, stop:1 #e0e0e0);"
            "border: 1px solid #b8b8b8;"
            "padding: 6px 20px;"
            "color: #444444;"
            "font-weight: normal;"
            "font-size: 11pt;"
            "}"
            "QPushButton:hover {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #ffffff, stop:1 #e8e8e8);"
            "}"
            "QPushButton:pressed {"
            "background-color: #d0d0d0;"
            "}"
        )
        self.preview_nc_btn.clicked.connect(self._preview_nc)

        self.generate_btn = QPushButton("GENERATE")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setStyleSheet(
            "QPushButton {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #4fd7ff, stop:1 #20b9f4);"
            "border: 1px solid #1aa3d8;"
            "padding: 6px 20px;"
            "color: white;"
            "font-weight: bold;"
            "font-size: 11pt;"
            "}"
            "QPushButton:hover {"
            "background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #6be0ff, stop:1 #32c3fc);"
            "}"
            "QPushButton:pressed {"
            "background-color: #1aa3d8;"
            "}"
        )
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        layout.addWidget(self.guidance_btn, alignment=Qt.AlignLeft)
        layout.addWidget(self.preview_nc_btn, alignment=Qt.AlignLeft)
        layout.addStretch()
        layout.addWidget(self.generate_btn, alignment=Qt.AlignRight)

        return w

    # -----------------------------
    # State sync
    # -----------------------------
    def _switch_tab(self, index):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def _populate_fields_from_state(self):
        self.csv_path_edit.setText(self.state.file.csv_path)

        self.model_scale_edit.setText(str(self.state.transform.model_scale))
        self.offset_x_edit.setText(str(self.state.transform.model_offset_x))
        self.offset_y_edit.setText(str(self.state.transform.model_offset_y))
        self.offset_z_edit.setText(str(self.state.transform.model_offset_z))

        self.radial_scale_edit.setText(str(self.state.transform.radial_scale))
        self.clearance_edit.setText(str(self.state.transform.clearance_z))

        self.program_number_edit.setText(str(self.state.machine.program_number))
        self.tool_number_edit.setText(str(self.state.machine.tool_number))
        self.b_angle_edit.setText(str(self.state.machine.b_angle))

        if self.state.machine.spindle_side == "SUB":
            self.spindle_side_combo.setCurrentIndex(1)
        else:
            self.spindle_side_combo.setCurrentIndex(0)

        self.feedrate_edit.setText(str(self.state.machine.feedrate))
        self.spindle_speed_edit.setText(str(self.state.machine.spindle_speed))

        self.spindle_dir_combo.setCurrentText(self.state.machine.spindle_dir)
        self.coolant_checkbox.setChecked(self.state.machine.coolant_on)
        self.cutter_comp_combo.setCurrentText(self.state.machine.cutter_comp)

        self.output_folder_edit.setText(self.state.machine.output_folder)
        self._update_program_file_label()

    def _update_state_from_fields(self):
        try:
            self.state.file.csv_path = self.csv_path_edit.text().strip()

            self.state.transform.model_scale = float(self.model_scale_edit.text())
            self.state.transform.model_offset_x = float(self.offset_x_edit.text())
            self.state.transform.model_offset_y = float(self.offset_y_edit.text())
            self.state.transform.model_offset_z = float(self.offset_z_edit.text())

            self.state.transform.radial_scale = float(self.radial_scale_edit.text())
            self.state.transform.clearance_z = float(self.clearance_edit.text())

            self.state.machine.program_number = int(self.program_number_edit.text())
            self.state.machine.tool_number = int(self.tool_number_edit.text())
            self.state.machine.b_angle = float(self.b_angle_edit.text())

            if self.spindle_side_combo.currentIndex() == 1:
                self.state.machine.spindle_side = "SUB"
            else:
                self.state.machine.spindle_side = "MAIN"

            self.state.machine.feedrate = float(self.feedrate_edit.text())
            self.state.machine.spindle_speed = float(self.spindle_speed_edit.text())
            self.state.machine.spindle_dir = self.spindle_dir_combo.currentText()

            self.state.machine.coolant_on = self.coolant_checkbox.isChecked()
            self.state.machine.cutter_comp = self.cutter_comp_combo.currentText()
            self.state.machine.output_folder = self.output_folder_edit.text().strip()

            self._update_program_file_label()
            return True
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Please check numeric fields.")
            return False

    def _update_program_file_label(self):
        pn = self.state.machine.program_number
        self.program_file_label.setText("O%04d_deburr.nc" % pn)

    # -----------------------------
    # File / folder handlers
    # -----------------------------
    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            self.csv_path_edit.setText(path)

    def _reload_csv(self):
        path = self.csv_path_edit.text().strip()
        if not path:
            QMessageBox.information(self, "No file", "No CSV path set.")
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Missing file", "File not found:\n%s" % path)
            return
        try:
            pts = deburr_tool.load_points(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to load CSV:\n%s" % e)
            return
        QMessageBox.information(self, "CSV loaded", "Loaded %d points." % len(pts))

    def _browse_output_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.output_folder_edit.text()
        )
        if path:
            self.output_folder_edit.setText(path)

    def _preview_nc_notice(self):
        QMessageBox.information(
            self,
            "Preview NC",
            "Preview is not implemented yet.\n"
            "Open the generated file in your editor."
        )

    # -----------------------------
    # Build NC text just for GUIDANCE
    # -----------------------------
    def _build_guidance_nc_text(self):
        """
        Build the preview NC text including:
        - JSON comment tags ;ORIGINAL_POINTS:[...]
        - JSON comment tags ;DEBURR_POINTS:[...]
        so the viewer can show both paths.
        """
        import json

        # Make sure state is in sync with the UI
        if not self._update_state_from_fields():
            return None

        csv_path = self.state.file.csv_path
        if not csv_path:
            QMessageBox.warning(self, "No CSV", "CSV path is not set.")
            return None
        if not os.path.isfile(csv_path):
            QMessageBox.warning(
                self, "Missing CSV",
                "CSV file not found:\n%s" % csv_path
            )
            return None

        # 1. Load raw CSV points
        try:
            points = deburr_tool.load_points(csv_path)
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "Failed to load CSV for preview:\n%s" % e
            )
            return None

        # Original path = raw model points (for the “Show original” button)
        original_points = [(float(x), float(y), float(z)) for (x, y, z) in points]

        # 2. Apply model scale + offset (same as in _on_generate_clicked)
        tr = self.state.transform
        points_model = deburr_tool.scale_and_offset_model(
            points,
            scale=tr.model_scale,
            dx=tr.model_offset_x,
            dy=tr.model_offset_y,
            dz=tr.model_offset_z,
        )

        # 3. Simple radial scale for preview (around X axis)
        radial = tr.radial_scale
        if abs(radial - 1.0) > 1e-6:
            deburr_points = []
            for (x, y, z) in points_model:
                r = (y**2 + z**2) ** 0.5
                if r == 0.0:
                    deburr_points.append((x, y, z))
                else:
                    new_r = r * radial
                    f = new_r / r
                    deburr_points.append((x, y * f, z * f))
        else:
            deburr_points = points_model

        # 4. Generate NC with deburr_points (same logic as _on_generate_clicked)
        mc = self.state.machine
        comp_mode = None if mc.cutter_comp == "NONE" else mc.cutter_comp

        if mc.spindle_side == "SUB":
            spindle_m_code = "M304"
            work_offset = "G57"
        else:
            spindle_m_code = "M303"
            work_offset = "G54"

        try:
            nc_lines = deburr_tool.generate_nc(
                deburr_points,
                program_number=mc.program_number,
                tool_number=mc.tool_number,
                b_angle=mc.b_angle,
                feed=mc.feedrate,
                spindle_speed=mc.spindle_speed,
                spindle_dir=mc.spindle_dir,
                coolant_on=mc.coolant_on,
                comp_mode=comp_mode,
                clearance=tr.clearance_z,
                radial_scale=tr.radial_scale,
                spindle_m_code=spindle_m_code,
                work_offset=work_offset,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "Failed to generate NC for preview:\n%s" % e
            )
            return None

        # 5. JSON headers for the viewer – this is what the JS uses
        header = [
            ";ORIGINAL_POINTS:" + json.dumps(original_points),
            ";DEBURR_POINTS:" + json.dumps(deburr_points),
        ]

        return "\n".join(header + nc_lines)

    # -----------------------------
    # Build NC text for NC PREVIEW (no JSON headers)
    # -----------------------------
    def _build_preview_nc_text(self):
        """
        Build NC text exactly like GENERATE, but return it as a string
        without any ;ORIGINAL_POINTS / ;DEBURR_POINTS comments.
        Used by the NC PREVIEW dialog.
        """
        # Make sure state is in sync with the UI
        if not self._update_state_from_fields():
            return None

        csv_path = self.state.file.csv_path
        if not csv_path:
            QMessageBox.warning(self, "No CSV", "CSV path is not set.")
            return None
        if not os.path.isfile(csv_path):
            QMessageBox.warning(
                self, "Missing CSV",
                "CSV file not found:\n%s" % csv_path
            )
            return None

        # 1. Load raw CSV points
        try:
            points = deburr_tool.load_points(csv_path)
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "Failed to load CSV for preview:\n%s" % e
            )
            return None

        # 2. Apply model scale + offset (same as in _on_generate_clicked)
        tr = self.state.transform
        points_model = deburr_tool.scale_and_offset_model(
            points,
            scale=tr.model_scale,
            dx=tr.model_offset_x,
            dy=tr.model_offset_y,
            dz=tr.model_offset_z
        )

        # 3. Generate NC (same logic as _on_generate_clicked)
        mc = self.state.machine
        comp_mode = None if mc.cutter_comp == "NONE" else mc.cutter_comp

        if mc.spindle_side == "SUB":
            spindle_m_code = "M304"
            work_offset = "G57"
        else:
            spindle_m_code = "M303"
            work_offset = "G54"

        try:
            nc_lines = deburr_tool.generate_nc(
                points_model,
                program_number=mc.program_number,
                tool_number=mc.tool_number,
                b_angle=mc.b_angle,
                feed=mc.feedrate,
                spindle_speed=mc.spindle_speed,
                spindle_dir=mc.spindle_dir,
                coolant_on=mc.coolant_on,
                comp_mode=comp_mode,
                clearance=tr.clearance_z,
                radial_scale=tr.radial_scale,
                spindle_m_code=spindle_m_code,
                work_offset=work_offset,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                "Failed to generate NC for preview:\n%s" % e
            )
            return None

        return "\n".join(nc_lines)


    # -----------------------------
    # GUIDANCE + GENERATE
    # -----------------------------
    def _toggle_guidance(self):
        """
        Toggle the embedded guidance preview on the Path & Geometry page.
        When opening, hide the input path and diagram, move the model/offset row to
        the bottom area, and show the 3D viewer with current NC preview.
        When closing, restore the original layout.
        """
        # Only applicable on the Path & Geometry tab (index 0)
        if self.nav_list.currentRow() != 0:
            # If not on the first tab, fallback to overlay behavior
            if self.guidance_overlay.isVisible():
                self.guidance_overlay.hide()
            else:
                nc_text = self._build_guidance_nc_text()
                if nc_text:
                    self.guidance_overlay.resize(self.centralWidget().size())
                    self.guidance_overlay.show()
                    self.guidance_overlay.set_gcode(nc_text)
            return

        if not self.guidance_open:
            # Opening guidance
            nc_text = self._build_guidance_nc_text()
            if not nc_text:
                return
            # Hide input path row controls
            self.path_input_label.hide()
            self.csv_path_edit.hide()
            self.path_browse_btn.hide()
            self.path_reload_btn.hide()
            # When guidance is open the fields widget (grid of other
            # inputs) contributes a large empty area on the left. Hide it
            # entirely so that the viewer can expand into this space.
            if self.path_fields_widget:
                self.path_fields_widget.hide()
            # Move the scale/offset row widget to the bottom guidance container
            try:
                self.path_grid.removeWidget(self.path_row_widget)
            except Exception:
                pass
            # Remove from any parent layout before re-adding
            self.path_row_widget.setParent(None)
            bottom_layout = self.path_guidance_bottom.layout()
            bottom_layout.addWidget(self.path_row_widget)
            # Hide the diagram while guidance is open
            if self.path_diagram:
                self.path_diagram.hide()
            # Show guidance container
            self.path_guidance_container.show()
            # Load HTML if not loaded yet and send NC text
            if self.path_guidance_viewer:
                if not self.guidance_html_loaded:
                    # Load HTML; pending gcode will be sent on load finish
                    self.pending_guidance_gcode = nc_text
                    self.path_guidance_viewer.setHtml(GCODE_VIEWER_HTML)
                else:
                    self._send_guidance_gcode(nc_text, update=False)
            # Update button label
            self.guidance_btn.setText("HIDE GUIDANCE")
            self.guidance_open = True
        else:
            # Closing guidance
            # Hide guidance container
            self.path_guidance_container.hide()
            # Remove row widget from bottom and put back into grid
            bottom_layout = self.path_guidance_bottom.layout()
            bottom_layout.removeWidget(self.path_row_widget)
            self.path_row_widget.setParent(self.path_fields_widget)
            self.path_grid.addWidget(self.path_row_widget, self.path_row_index, 0, 1, 3)
            # Show input path controls
            self.path_input_label.show()
            self.csv_path_edit.show()
            self.path_browse_btn.show()
            self.path_reload_btn.show()
            # Show diagram again
            if self.path_diagram:
                self.path_diagram.show()

            # Restore the fields widget visibility when guidance is closed
            if self.path_fields_widget:
                self.path_fields_widget.show()
            # Update button label
            self.guidance_btn.setText("GUIDANCE")
            self.guidance_open = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.guidance_overlay.isVisible():
            self.guidance_overlay.resize(self.centralWidget().size())

    def _on_generate_clicked(self):
        if not self._update_state_from_fields():
            return

        csv_path = self.state.file.csv_path
        if not csv_path:
            QMessageBox.warning(self, "No CSV", "CSV path is not set.")
            return
        if not os.path.isfile(csv_path):
            QMessageBox.warning(self, "Missing CSV", "CSV file not found:\n%s" % csv_path)
            return

        try:
            points = deburr_tool.load_points(csv_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to load CSV:\n%s" % e)
            return

        tr = self.state.transform
        points_model = deburr_tool.scale_and_offset_model(
            points,
            scale=tr.model_scale,
            dx=tr.model_offset_x,
            dy=tr.model_offset_y,
            dz=tr.model_offset_z
        )

        mc = self.state.machine
        comp_mode = None if mc.cutter_comp == "NONE" else mc.cutter_comp

        if mc.spindle_side == "SUB":
            spindle_m_code = "M304"
            work_offset = "G57"
        else:
            spindle_m_code = "M303"
            work_offset = "G54"

        try:
            nc_lines = deburr_tool.generate_nc(
                points_model,
                program_number=mc.program_number,
                tool_number=mc.tool_number,
                b_angle=mc.b_angle,
                feed=mc.feedrate,
                spindle_speed=mc.spindle_speed,
                spindle_dir=mc.spindle_dir,
                coolant_on=mc.coolant_on,
                comp_mode=comp_mode,
                clearance=tr.clearance_z,
                radial_scale=tr.radial_scale,
                spindle_m_code=spindle_m_code,
                work_offset=work_offset,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to generate NC:\n%s" % e)
            return

        out_dir = mc.output_folder
        os.makedirs(out_dir, exist_ok=True)

        out_name = "O%04d_deburr.nc" % mc.program_number
        out_path = os.path.join(out_dir, out_name)

        try:
            with open(out_path, "w") as f:
                for line in nc_lines:
                    f.write(line + "\n")
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to write NC file:\n%s" % e)
            return

        save_settings(self.state)

        QMessageBox.information(
            self,
            "Done",
            "NC program written to:\n%s" % out_path
        )

# -----------------------------------------------------------
# Entry point
# -----------------------------------------------------------

def main():
    csv_override = None
    if len(sys.argv) > 1:
        csv_override = sys.argv[1]

    app = QApplication(sys.argv)

    app.setStyleSheet("""
        /* GLOBAL FONT */
        * {
            font-family: 'Segoe UI';
            font-size: 10pt;
        }

        /* LABELS – slightly bold like CELOS */
        QLabel {
            font-weight: 400;
        }

        /* TEXT FIELDS – white like VPS */
        QLineEdit {
            font-size: 10pt;
            font-family: 'Segoe UI';
            font-weight: 100;
            background-color: #ffffff;
            border: 1px solid #c8c8c8;
            padding: 2px 4px;
        }

        QLineEdit:focus {
            border: 1px solid #4a90e2;
            background-color: #ffffff;
        }

        /* COMBOBOX – white background, subtle border */
        QComboBox {
            font-size: 10pt;
            font-family: 'Segoe UI';
            background-color: #ffffff;
            border: 1px solid #c8c8c8;
            padding: 2px 4px;
            min-height: 26px;
        }

        QComboBox:focus {
            border: 1px solid #4a90e2;
            background-color: #ffffff;
        }

        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 16px;
            border-left: 1px solid #c8c8c8;
        }

        /* minimal arrow */
        QComboBox::down-arrow {
            image: none;
        }

        /* popup list (the part that was black) */
        QComboBox QAbstractItemView {
            background-color: #f7f7f7;
            color: #000000;
            selection-background-color: #4a90e2;
            selection-color: #ffffff;
            border: 1px solid #c8c8c8;
        }

        /* BUTTON FONT SIZES (button colors are set elsewhere) */
        QPushButton {
            font-size: 11pt;
            font-family: 'Segoe UI';
        }
    """)

    win = MainWindow(csv_override=csv_override)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
