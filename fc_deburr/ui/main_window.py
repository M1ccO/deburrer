from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QInputDialog,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..application.job_metrics import estimate_job, format_metrics
from ..application.session import DeburrSession
from ..domain.models import (
    FaceRegion,
    MotionMode,
    Operation,
    PositioningMode,
    ToolDefinition,
    ToolKind,
)
from ..machine.post_ntx import NtxPostSettings
from ..machine.profiles import MachineProfile
from .backplot_view import BackplotView
from .presets import ToolPresetStore
from .rotary_plot import RotaryPlotWidget
from .settings import load_ui_settings, save_ui_settings
from .web_preview import WebPreviewWidget as CamViewport


class MainWindow(QMainWindow):
    def __init__(self, feature_path=None):
        super().__init__()
        self.session = DeburrSession()
        self.profile = MachineProfile()
        self.presets = ToolPresetStore()
        self.setWindowTitle("NTX Deburr Engine")
        self.resize(1180, 760)
        self._build_ui()
        self._restore_settings()
        if feature_path:
            self._load_feature(feature_path)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_controls())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.scene_view = CamViewport()
        right_layout.addWidget(self.scene_view, 3)
        self.tabs = QTabWidget()
        self.backplot = BackplotView()
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.nc_text = QTextEdit()
        self.nc_text.setReadOnly(True)
        self.rotary_plot = RotaryPlotWidget()
        self.tabs.addTab(self.backplot, "Backplot")
        self.tabs.addTab(self.rotary_plot, "B / C Plot")
        self.tabs.addTab(self.status_text, "Job Summary")
        self.tabs.addTab(self.nc_text, "NC Output")
        right_layout.addWidget(self.tabs, 2)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.scene_view.playIndexChanged.connect(self.backplot.set_play_index)

    def _build_controls(self):
        content = QWidget()
        layout = QVBoxLayout(content)

        feature_box = QGroupBox("Feature job — owns source geometry")
        feature_form = QFormLayout(feature_box)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.feature_path = QLineEdit()
        self.feature_path.setReadOnly(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_feature)
        row_layout.addWidget(self.feature_path, 1)
        row_layout.addWidget(browse)
        feature_form.addRow("JSON", row)
        self.feature_summary = QLabel("No feature loaded")
        self.feature_summary.setWordWrap(True)
        feature_form.addRow(self.feature_summary)
        layout.addWidget(feature_box)

        tool_box = QGroupBox("Tool definition")
        tool_form = QFormLayout(tool_box)
        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(self.presets.names())
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        save_preset = QPushButton("Save as…")
        save_preset.clicked.connect(self._save_preset)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(save_preset)
        self.tool_kind = QComboBox()
        self.tool_kind.addItem("Chamfer mill", ToolKind.CHAMFER.value)
        self.tool_kind.addItem("Ball end mill", ToolKind.BALL.value)
        self.tool_kind.currentIndexChanged.connect(self._tool_kind_changed)
        self.tool_id = QLineEdit("C90")
        self.diameter = self._double(6.0, 0.001, 1000.0, 3)
        self.stickout = self._double(25.0, 0.001, 1000.0, 3)
        self.cutting_length = self._double(0.0, 0.0, 1000.0, 3)
        self.cutting_length.setSpecialValueText("auto")
        self.included_angle = self._double(90.0, 1.0, 179.0, 3)
        self.tip_flat = self._double(0.0, 0.0, 100.0, 3)
        self.contact_radius = self._double(0.5, 0.001, 500.0, 3)
        self.radial_correction = self._double(0.0, -10.0, 10.0, 4)
        self.axial_correction = self._double(0.0, -10.0, 10.0, 4)
        tool_form.addRow("Preset", preset_row)
        tool_form.addRow("Type", self.tool_kind)
        tool_form.addRow("Tool ID", self.tool_id)
        tool_form.addRow("Diameter (mm)", self.diameter)
        tool_form.addRow("Stickout (mm)", self.stickout)
        tool_form.addRow("Cutting length (mm)", self.cutting_length)
        tool_form.addRow("Included angle", self.included_angle)
        tool_form.addRow("Tip flat diameter", self.tip_flat)
        tool_form.addRow("Contact radius", self.contact_radius)
        tool_form.addRow("Radial calibration", self.radial_correction)
        tool_form.addRow("Axial calibration", self.axial_correction)
        layout.addWidget(tool_box)

        op_box = QGroupBox("Operation — owns requested result")
        op_form = QFormLayout(op_box)
        self.chamfer_width = self._double(0.5, 0.001, 100.0, 3)
        self.ball_break_width = self._double(0.25, 0.001, 100.0, 3)
        self.feed = self._double(800.0, 0.001, 100000.0, 3)
        self.lead = self._double(0.0, -180.0, 180.0, 3)
        self.tilt = self._double(0.0, -90.0, 90.0, 3)
        self.lead_in = self._double(2.0, 0.0, 1000.0, 3)
        self.lead_out = self._double(2.0, 0.0, 1000.0, 3)
        self.safety_lift = self._double(3.0, 0.001, 1000.0, 3)
        self.positioning_mode = QComboBox()
        self.positioning_mode.addItem(
            "Tangent Positioning", PositioningMode.TANGENT.value
        )
        self.positioning_mode.addItem(
            "Center Positioning", PositioningMode.CENTER.value
        )
        self.flip_side = QCheckBox("Flip calculated deburr side")
        self.motion_mode = QComboBox()
        self.motion_mode.addItem(
            "True 3+2 (fixed B and C)",
            MotionMode.INDEXED_3_PLUS_2.value,
        )
        self.motion_mode.addItem(
            "4+1 (fixed C, continuous B)",
            MotionMode.SIMULTANEOUS_4_PLUS_1.value,
        )
        self.motion_mode.addItem(
            "5-Axis Simultaneous",
            MotionMode.SIMULTANEOUS_5_AXIS.value,
        )
        self.motion_mode.currentIndexChanged.connect(
            self._motion_mode_changed
        )
        self.auto_index = QCheckBox("Calculate indexed angles")
        self.auto_index.setChecked(True)
        self.auto_index.toggled.connect(self._motion_mode_changed)
        self.indexed_b = self._double(0.0, -120.0, 120.0, 3)
        self.indexed_c = self._double(0.0, -9999.0, 9999.0, 3)
        op_form.addRow("Equal chamfer width", self.chamfer_width)
        op_form.addRow("Rounded break width", self.ball_break_width)
        op_form.addRow("Feed", self.feed)
        op_form.addRow("Lead angle", self.lead)
        op_form.addRow("Tilt angle", self.tilt)
        op_form.addRow("Lead-in length", self.lead_in)
        op_form.addRow("Lead-out length", self.lead_out)
        op_form.addRow("Safety lift", self.safety_lift)
        op_form.addRow("Approach strategy", self.positioning_mode)
        op_form.addRow("Motion mode", self.motion_mode)
        op_form.addRow("Indexed posture", self.auto_index)
        op_form.addRow("Indexed B", self.indexed_b)
        op_form.addRow("Indexed C", self.indexed_c)
        op_form.addRow("Side", self.flip_side)
        layout.addWidget(op_box)
        self._apply_preset(self.preset_combo.currentText())
        self._motion_mode_changed()

        surface_box = QGroupBox("Face Finishing")
        surface_form = QFormLayout(surface_box)
        self.surface_tolerance = self._double(0.01, 0.0001, 10.0, 4)
        self.surface_direction = QComboBox()
        self.surface_direction.addItem("Automatic (long direction)", "auto")
        self.surface_direction.addItem("Along surface U", "u")
        self.surface_direction.addItem("Along surface V", "v")
        self.path_sample_spacing = self._double(0.5, 0.01, 100.0, 3)
        surface_form.addRow("Maximum scallop height", self.surface_tolerance)
        surface_form.addRow("Pass direction", self.surface_direction)
        surface_form.addRow("Point spacing", self.path_sample_spacing)
        self.surface_box = surface_box
        layout.addWidget(surface_box)

        post_box = QGroupBox("NTX post")
        post_form = QFormLayout(post_box)
        self.program_number = QSpinBox()
        self.program_number.setRange(1, 9999)
        self.program_number.setValue(9001)
        self.tool_code = QLineEdit("T6456.")
        self.work_offset = QComboBox()
        self.work_offset.addItems(["G54", "G55", "G56", "G57"])
        self.h_offset = QSpinBox()
        self.h_offset.setRange(1, 999)
        self.h_offset.setValue(1)
        self.tcp_d = QSpinBox()
        self.tcp_d.setRange(0, 999)
        self.tcp_d.setValue(9)
        self.spindle_speed = QSpinBox()
        self.spindle_speed.setRange(1, 100000)
        self.spindle_speed.setValue(6000)
        self.spindle_direction = QComboBox()
        self.spindle_direction.addItems(["M03", "M04"])
        self.coolant_on = QCheckBox("M08")
        self.coolant_on.setChecked(True)
        post_form.addRow("Program", self.program_number)
        post_form.addRow("Tool code", self.tool_code)
        post_form.addRow("Work offset", self.work_offset)
        post_form.addRow("H offset", self.h_offset)
        post_form.addRow("TCP D", self.tcp_d)
        post_form.addRow("Spindle RPM", self.spindle_speed)
        post_form.addRow("Spindle direction", self.spindle_direction)
        post_form.addRow("Coolant", self.coolant_on)
        layout.addWidget(post_box)

        calculate = QPushButton("CALCULATE AND VALIDATE")
        calculate.clicked.connect(self._calculate)
        save_nc = QPushButton("SAVE VALIDATED NC…")
        save_nc.clicked.connect(self._save_nc)
        layout.addWidget(calculate)
        layout.addWidget(save_nc)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(390)
        return scroll

    def _double(self, value, minimum, maximum, decimals):
        widget = QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(0.1)
        return widget

    def _browse_feature(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open deburr feature", "", "Deburr feature (*.json)"
        )
        if path:
            self._load_feature(path)

    def _load_feature(self, path):
        try:
            feature = self.session.load_feature(path)
        except Exception as error:
            QMessageBox.critical(self, "Feature load failed", str(error))
            return
        self.feature_path.setText(str(path))
        stl_path = _display_stl_path(Path(path))
        self.scene_view.set_workpiece_stl(
            str(stl_path) if stl_path is not None else None
        )
        if isinstance(feature, FaceRegion):
            self.feature_summary.setText(
                "%s\nFACE FINISHING • %d selected face%s"
                % (
                    feature.source_object_id or feature.id,
                    len(feature.patches),
                    "" if len(feature.patches) == 1 else "s",
                )
            )
            ball_index = self.tool_kind.findData(ToolKind.BALL.value)
            self.tool_kind.setCurrentIndex(ball_index)
            self.tool_kind.setEnabled(False)
            self.surface_box.setEnabled(True)
            self.positioning_mode.setEnabled(False)
            self.flip_side.setEnabled(False)
        else:
            self.feature_summary.setText(
                "%s\nWIRE DEBURR • %d samples • C0 %s"
                % (
                    feature.source_object_id or feature.id,
                    len(feature.samples),
                    feature.c0_vertex_id or "automatic",
                )
            )
            self.tool_kind.setEnabled(True)
            self.surface_box.setEnabled(False)
            self.positioning_mode.setEnabled(True)
            self.flip_side.setEnabled(True)
        self.scene_view.set_document(None)
        self.backplot.set_document(None)
        self.rotary_plot.set_document(None)
        self.nc_text.clear()
        self.status_text.setPlainText("Feature loaded. Calculate to create a new owned path.")

    def _calculate(self):
        try:
            tool = self._tool_definition()
            operation = self._operation(tool)
            result = self.session.calculate(
                tool, operation, self.profile
            )
            settings = self._post_settings()
            nc = self.session.post(self.profile, settings)
        except Exception as error:
            self.status_text.setPlainText("BLOCKED\n\n%s" % error)
            self.tabs.setCurrentWidget(self.status_text)
            QMessageBox.warning(self, "Calculation blocked", str(error))
            return

        self.scene_view.set_document(self.session.preview)
        self.backplot.set_document(self.session.preview)
        self.rotary_plot.set_document(self.session.preview)
        self.scene_view.set_tool(
            "chamfer" if tool.kind is ToolKind.CHAMFER else "ball",
            tool.diameter,
            tool.stickout,
            tool.cutting_length,
            tool.included_angle_deg,
            tool.tip_flat_diameter,
        )
        if result.indexed_b_deg is not None:
            self.indexed_b.setValue(result.indexed_b_deg)
        if result.indexed_c_deg is not None:
            self.indexed_c.setValue(result.indexed_c_deg)
        self.nc_text.setPlainText(nc)
        try:
            metrics = estimate_job(
                self.session.feature,
                result.machine_path,
                self.profile,
                model_path=result.model_path,
            )
            text = format_metrics(metrics, self.profile)
        except Exception as error:
            text = "Job metrics unavailable: %s" % error
        if result.side_auto_picked:
            text += (
                "\n\nAUTO-SIDE: engine picked flip_side=%s because the B "
                "envelope rejected the requested side.  Uncheck "
                "'Flip calculated deburr side' to override."
                % result.side_used
            )
        if result.machine_path.warnings:
            text += "\n\nSolver warnings:\n"
            for warning in result.machine_path.warnings:
                text += "  - " + warning + "\n"
        self.status_text.setPlainText(text)
        self._save_settings()

    def _save_nc(self):
        if not self.session.nc_text:
            self._calculate()
        if not self.session.nc_text:
            return
        default = "O%04d_deburr.nc" % self.program_number.value()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save validated NC", default, "NC program (*.nc)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self.session.nc_text, encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Save failed", str(error))
            return
        QMessageBox.information(self, "NC saved", path)

    def _tool_definition(self):
        kind = ToolKind(self.tool_kind.currentData())
        return ToolDefinition(
            id=self.tool_id.text().strip() or kind.value,
            kind=kind,
            diameter=self.diameter.value(),
            stickout=self.stickout.value(),
            cutting_length=self.cutting_length.value(),
            included_angle_deg=(
                self.included_angle.value() if kind is ToolKind.CHAMFER else None
            ),
            tip_flat_diameter=(
                self.tip_flat.value() if kind is ToolKind.CHAMFER else 0.0
            ),
            contact_radius=(
                self.contact_radius.value() if kind is ToolKind.CHAMFER else None
            ),
            radial_correction=self.radial_correction.value(),
            axial_correction=self.axial_correction.value(),
        )

    def _operation(self, tool):
        return Operation(
            id="ui_operation",
            tool_id=tool.id,
            target_width=(
                self.chamfer_width.value()
                if tool.kind is ToolKind.CHAMFER
                else None
            ),
            ball_engagement=None,
            ball_break_width=(
                self.ball_break_width.value()
                if tool.kind is ToolKind.BALL
                else None
            ),
            feed=self.feed.value(),
            lead_deg=self.lead.value(),
            tilt_deg=(
                self.tilt.value() if tool.kind is ToolKind.BALL else 0.0
            ),
            lead_in_length=self.lead_in.value(),
            lead_out_length=self.lead_out.value(),
            safety_lift=self.safety_lift.value(),
            positioning_mode=PositioningMode(
                self.positioning_mode.currentData()
            ),
            flip_side=self.flip_side.isChecked(),
            motion_mode=MotionMode(self.motion_mode.currentData()),
            auto_index=self.auto_index.isChecked(),
            indexed_b_deg=(
                None
                if self.auto_index.isChecked()
                else self.indexed_b.value()
            ),
            indexed_c_deg=(
                None
                if self.auto_index.isChecked()
                else self.indexed_c.value()
            ),
            surface_tolerance=self.surface_tolerance.value(),
            surface_direction=self.surface_direction.currentData(),
            path_sample_spacing=self.path_sample_spacing.value(),
        )

    def _post_settings(self):
        return NtxPostSettings(
            program_number=self.program_number.value(),
            tool_code=self.tool_code.text().strip(),
            work_offset=self.work_offset.currentText(),
            h_offset=self.h_offset.value(),
            tcp_d=self.tcp_d.value(),
            spindle_speed=self.spindle_speed.value(),
            spindle_direction=self.spindle_direction.currentText(),
            coolant_on=self.coolant_on.isChecked(),
        )

    def _tool_kind_changed(self):
        chamfer = ToolKind(self.tool_kind.currentData()) is ToolKind.CHAMFER
        for widget in (
            self.included_angle,
            self.tip_flat,
            self.contact_radius,
            self.radial_correction,
            self.axial_correction,
            self.chamfer_width,
        ):
            widget.setEnabled(chamfer)
        self.ball_break_width.setEnabled(not chamfer)
        self.tilt.setEnabled(not chamfer)
        self.tilt.setToolTip(
            "Ball posture tilt"
            if not chamfer
            else "Disabled: cone tilt would change the requested flat chamfer"
        )
        if chamfer and self.tool_id.text().startswith("B"):
            self.tool_id.setText("C90")
        elif not chamfer and self.tool_id.text().startswith("C"):
            self.tool_id.setText("B6")
        self._motion_mode_changed()

    def _motion_mode_changed(self, *args):
        mode = MotionMode(self.motion_mode.currentData())
        automatic = self.auto_index.isChecked()
        ball = ToolKind(self.tool_kind.currentData()) is ToolKind.BALL
        cardinal_ball = ball and mode is MotionMode.INDEXED_3_PLUS_2
        self.lead.setEnabled(not cardinal_ball)
        self.tilt.setEnabled(ball and not cardinal_ball)
        if cardinal_ball:
            self.lead.setValue(0.0)
            self.tilt.setValue(0.0)
        posture_tip = (
            "Indexed ball mode uses fixed B0/B±90; local lead and tilt "
            "do not apply"
            if cardinal_ball
            else ""
        )
        self.lead.setToolTip(posture_tip)
        self.tilt.setToolTip(
            posture_tip
            if cardinal_ball
            else (
                "Ball posture tilt"
                if ball
                else "Disabled: cone tilt would change the flat chamfer"
            )
        )
        self.auto_index.setEnabled(
            mode is not MotionMode.SIMULTANEOUS_5_AXIS
        )
        self.indexed_b.setEnabled(
            mode is MotionMode.INDEXED_3_PLUS_2 and not automatic
        )
        self.indexed_c.setEnabled(
            mode
            in (
                MotionMode.INDEXED_3_PLUS_2,
                MotionMode.SIMULTANEOUS_4_PLUS_1,
            )
            and not automatic
        )

    def _preset_values(self):
        return {
            "kind": ToolKind(self.tool_kind.currentData()).value,
            "tool_id": self.tool_id.text().strip(),
            "diameter": self.diameter.value(),
            "stickout": self.stickout.value(),
            "included_angle": self.included_angle.value(),
            "tip_flat": self.tip_flat.value(),
            "contact_radius": self.contact_radius.value(),
            "radial_correction": self.radial_correction.value(),
            "axial_correction": self.axial_correction.value(),
        }

    def _apply_preset(self, name):
        value = self.presets.get(name)
        if not value:
            return
        kind = ToolKind(value["kind"])
        index = self.tool_kind.findData(kind.value)
        if index >= 0:
            self.tool_kind.setCurrentIndex(index)
        self.tool_id.setText(value.get("tool_id", kind.value))
        self.diameter.setValue(value["diameter"])
        self.stickout.setValue(value["stickout"])
        self.radial_correction.setValue(value.get("radial_correction", 0.0))
        self.axial_correction.setValue(value.get("axial_correction", 0.0))
        if kind is ToolKind.CHAMFER:
            self.included_angle.setValue(value["included_angle"])
            self.tip_flat.setValue(value.get("tip_flat", 0.0))
            self.contact_radius.setValue(value["contact_radius"])

    def _save_preset(self):
        name, accepted = QInputDialog.getText(
            self, "Save tool preset", "Preset name:"
        )
        if not accepted or not name.strip():
            return
        try:
            self.presets.save(name, self._preset_values())
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Preset save failed", str(error))
            return
        if self.preset_combo.findText(name) < 0:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)

    def _settings_value(self):
        return {
            "tool_kind": ToolKind(self.tool_kind.currentData()).value,
            "tool_id": self.tool_id.text(),
            "diameter": self.diameter.value(),
            "stickout": self.stickout.value(),
            "included_angle": self.included_angle.value(),
            "tip_flat": self.tip_flat.value(),
            "contact_radius": self.contact_radius.value(),
            "radial_correction": self.radial_correction.value(),
            "axial_correction": self.axial_correction.value(),
            "chamfer_width": self.chamfer_width.value(),
            "ball_break_width": self.ball_break_width.value(),
            "feed": self.feed.value(),
            "lead": self.lead.value(),
            "tilt": self.tilt.value(),
            "lead_in": self.lead_in.value(),
            "lead_out": self.lead_out.value(),
            "safety_lift": self.safety_lift.value(),
            "positioning_mode": self.positioning_mode.currentData(),
            "motion_mode": self.motion_mode.currentData(),
            "auto_index": self.auto_index.isChecked(),
            "indexed_b": self.indexed_b.value(),
            "indexed_c": self.indexed_c.value(),
            "flip_side": self.flip_side.isChecked(),
            "surface_tolerance": self.surface_tolerance.value(),
            "surface_direction": self.surface_direction.currentData(),
            "path_sample_spacing": self.path_sample_spacing.value(),
            "program_number": self.program_number.value(),
            "tool_code": self.tool_code.text(),
            "work_offset": self.work_offset.currentText(),
            "h_offset": self.h_offset.value(),
            "tcp_d": self.tcp_d.value(),
            "spindle_speed": self.spindle_speed.value(),
            "spindle_direction": self.spindle_direction.currentText(),
            "coolant_on": self.coolant_on.isChecked(),
        }

    def _save_settings(self):
        save_ui_settings(self._settings_value())

    def _restore_settings(self):
        value = load_ui_settings()
        kind = value.get("tool_kind")
        if kind:
            index = self.tool_kind.findData(ToolKind(kind).value)
            if index >= 0:
                self.tool_kind.setCurrentIndex(index)
        fields = {
            "tool_id": self.tool_id,
            "tool_code": self.tool_code,
        }
        for key, widget in fields.items():
            if key in value:
                widget.setText(str(value[key]))
        numeric = {
            "diameter": self.diameter,
            "stickout": self.stickout,
            "included_angle": self.included_angle,
            "tip_flat": self.tip_flat,
            "contact_radius": self.contact_radius,
            "radial_correction": self.radial_correction,
            "axial_correction": self.axial_correction,
            "chamfer_width": self.chamfer_width,
            "ball_break_width": self.ball_break_width,
            "feed": self.feed,
            "lead": self.lead,
            "tilt": self.tilt,
            "lead_in": self.lead_in,
            "lead_out": self.lead_out,
            "safety_lift": self.safety_lift,
            "program_number": self.program_number,
            "h_offset": self.h_offset,
            "tcp_d": self.tcp_d,
            "spindle_speed": self.spindle_speed,
            "surface_tolerance": self.surface_tolerance,
            "path_sample_spacing": self.path_sample_spacing,
            "indexed_b": self.indexed_b,
            "indexed_c": self.indexed_c,
        }
        for key, widget in numeric.items():
            if key in value:
                widget.setValue(value[key])
        if (
            "ball_break_width" not in value
            and "ball_engagement" in value
        ):
            self.ball_break_width.setValue(value["ball_engagement"])
        if "work_offset" in value:
            self.work_offset.setCurrentText(value["work_offset"])
        if "positioning_mode" in value:
            index = self.positioning_mode.findData(value["positioning_mode"])
            if index >= 0:
                self.positioning_mode.setCurrentIndex(index)
        saved_mode = value.get("motion_mode")
        if saved_mode is None:
            saved_mode = (
                MotionMode.SIMULTANEOUS_5_AXIS.value
                if value.get("c_axis_mode") == "simultaneous"
                else MotionMode.INDEXED_3_PLUS_2.value
            )
        if saved_mode:
            index = self.motion_mode.findData(saved_mode)
            if index >= 0:
                self.motion_mode.setCurrentIndex(index)
        if "auto_index" in value:
            self.auto_index.setChecked(bool(value["auto_index"]))
        if "flip_side" in value:
            self.flip_side.setChecked(bool(value["flip_side"]))
        if "surface_direction" in value:
            index = self.surface_direction.findData(value["surface_direction"])
            if index >= 0:
                self.surface_direction.setCurrentIndex(index)
        self.surface_box.setEnabled(False)
        if "spindle_direction" in value:
            self.spindle_direction.setCurrentText(value["spindle_direction"])
        if "coolant_on" in value:
            self.coolant_on.setChecked(bool(value["coolant_on"]))
        self._tool_kind_changed()
        self._motion_mode_changed()


def _display_stl_path(feature_path):
    """Prefer a newer, lighter FreeCAD ``(Meshed)`` display export."""

    exact = feature_path.with_suffix(".stl")
    meshed = tuple(
        feature_path.parent.glob("* (Meshed).stl")
    )
    if meshed:
        candidate = min(
            meshed, key=lambda item: item.stat().st_size
        )
        if (
            not exact.is_file()
            or (
                candidate.stat().st_mtime >= exact.stat().st_mtime
                and candidate.stat().st_size < exact.stat().st_size
            )
        ):
            return candidate
    return exact if exact.is_file() else None
