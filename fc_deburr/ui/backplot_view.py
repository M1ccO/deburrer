from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..preview.models import PreviewDocument


class BackplotView(QWidget):
    """Top-down (X-Y) 2D backplot for quick path-order inspection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Optional[PreviewDocument] = None
        self._play_index = 0
        self.setMinimumHeight(180)
        self.setToolTip("Top-down backplot: drag = scroll, wheel = zoom")

    def set_document(self, document: Optional[PreviewDocument]) -> None:
        self._document = document
        self._play_index = 0
        self.update()

    def set_play_index(self, index: int) -> None:
        self._play_index = index
        self.update()

    def play_index(self) -> int:
        return self._play_index

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#111417"))
            painter.setRenderHint(QPainter.Antialiasing, True)

            if self._document is None:
                painter.setPen(QColor("#9aa4ad"))
                painter.drawText(
                    self.rect(), Qt.AlignCenter, "No toolpath"
                )
                return

            margin = 48.0
            area = QRectF(
                margin,
                12.0,
                max(1.0, self.width() - 2.0 * margin),
                max(1.0, self.height() - margin - 28.0),
            )

            xs, ys = self._compute_bounds()
            if not xs:
                painter.setPen(QColor("#9aa4ad"))
                painter.drawText(
                    self.rect(), Qt.AlignCenter, "No geometry"
                )
                return

            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            xpad = (xmax - xmin) * 0.05 or 1.0
            ypad = (ymax - ymin) * 0.05 or 1.0
            xmin -= xpad
            xmax += xpad
            ymin -= ypad
            ymax += ypad

            self._draw_grid(painter, area, xmin, xmax, ymin, ymax)

            for polyline in self._document.polylines:
                if not polyline.points:
                    continue
                name = polyline.name.lower()
                if "source" in name:
                    color = "#00d7ff"
                elif "contact" in name:
                    color = "#65e572"
                elif "cutter reference" in name or "cutter" in name:
                    color = "#ffd23f"
                elif "approach" in name or "retract" in name:
                    self._draw_poly(
                        painter, polyline.points, "#ff6868",
                        area, xmin, xmax, ymin, ymax, dashed=True,
                    )
                    continue
                else:
                    color = "#5a6168"
                self._draw_poly(
                    painter, polyline.points, color,
                    area, xmin, xmax, ymin, ymax,
                )

            self._draw_trail(painter, area, xmin, xmax, ymin, ymax)
            self._draw_cursor(painter, area, xmin, xmax, ymin, ymax)
            self._draw_spindle_indicator(painter, area, xmin, xmax, ymin, ymax)
            self._draw_legend(painter)
        finally:
            painter.end()

    def _compute_bounds(self):
        xs = []
        ys = []
        for polyline in self._document.polylines:
            for pt in polyline.points:
                xs.append(pt[0])
                ys.append(pt[1])
        return xs, ys

    def _transform(
        self, x: float, y: float,
        area: QRectF, xmin: float, xmax: float,
        ymin: float, ymax: float,
    ) -> QPointF:
        sx = (xmax - xmin) or 1.0
        sy = (ymax - ymin) or 1.0
        return QPointF(
            area.left() + area.width() * (x - xmin) / sx,
            area.bottom() - area.height() * (y - ymin) / sy,
        )

    def _draw_poly(
        self, painter, points, color,
        area, xmin, xmax, ymin, ymax, dashed=False,
    ) -> None:
        if len(points) < 2:
            return
        pen = QPen(QColor(color), 1.6)
        if dashed:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        path = QPainterPath()
        first = self._transform(
            points[0][0], points[0][1], area, xmin, xmax, ymin, ymax
        )
        path.moveTo(first)
        for pt in points[1:]:
            path.lineTo(self._transform(
                pt[0], pt[1], area, xmin, xmax, ymin, ymax
            ))
        painter.drawPath(path)

    def _draw_trail(self, painter, area, xmin, xmax, ymin, ymax) -> None:
        poses = self._document.tool_poses
        if not poses or self._play_index <= 0:
            return
        last = min(self._play_index, len(poses) - 1)
        trail_pts = [
            self._transform(
                p.cutter_reference[0],
                p.cutter_reference[1],
                area, xmin, xmax, ymin, ymax,
            )
            for p in list(poses[: last + 1])
        ]
        if len(trail_pts) < 2:
            # draw at least a dot at current position
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ff9f43"))
            painter.drawEllipse(trail_pts[0], 3.0, 3.0)
            return
        pen = QPen(QColor("#ff9f43"), 2.2)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(trail_pts[0])
        for pt in trail_pts[1:]:
            path.lineTo(pt)
        painter.drawPath(path)

    def _draw_cursor(self, painter, area, xmin, xmax, ymin, ymax) -> None:
        poses = self._document.tool_poses
        if not poses:
            return
        idx = max(0, min(self._play_index, len(poses) - 1))
        ref = poses[idx].cutter_reference
        pt = self._transform(
            ref[0], ref[1], area, xmin, xmax, ymin, ymax
        )
        painter.setPen(QPen(QColor("#ffffff"), 1.2))
        painter.setBrush(QColor("#ffd23f"))
        painter.drawEllipse(pt, 4.0, 4.0)

    def _draw_spindle_indicator(
        self, painter, area, xmin, xmax, ymin, ymax,
    ) -> None:
        origin = self._document.spindle_origin
        axis = self._document.spindle_axis
        start = self._transform(
            origin[0], origin[1], area, xmin, xmax, ymin, ymax
        )
        end = self._transform(
            origin[0] + axis[0] * 10.0,
            origin[1] + axis[1] * 10.0,
            area, xmin, xmax, ymin, ymax,
        )
        painter.setPen(QPen(QColor("#55ff55"), 1.0))
        painter.drawLine(start, end)
        painter.setBrush(QColor("#55ff55"))
        painter.drawEllipse(end, 3.0, 3.0)

    def _draw_grid(
        self, painter, area, xmin, xmax, ymin, ymax,
    ) -> None:
        step = max(
            1.0,
            ((xmax - xmin) + (ymax - ymin)) * 0.1,
        )
        painter.setPen(QPen(QColor("#2c3138"), 0.5))
        steps_x = int((xmax - xmin) / step) + 1
        steps_y = int((ymax - ymin) / step) + 1
        for i in range(-steps_x, steps_x * 2 + 1):
            x = xmin - step + i * step
            painter.drawLine(
                self._transform(x, ymin, area, xmin, xmax, ymin, ymax).toPoint(),
                self._transform(x, ymax, area, xmin, xmax, ymin, ymax).toPoint(),
            )
        for i in range(-steps_y, steps_y * 2 + 1):
            y = ymin - step + i * step
            painter.drawLine(
                self._transform(xmin, y, area, xmin, xmax, ymin, ymax).toPoint(),
                self._transform(xmax, y, area, xmin, xmax, ymin, ymax).toPoint(),
            )

    def _draw_legend(self, painter) -> None:
        painter.setFont(painter.font())
        x = 10
        y = self.height() - 14
        for color, label in (
            ("#00d7ff", "Source"),
            ("#65e572", "Contact"),
            ("#ffd23f", "Cutter"),
            ("#ff9f43", "Trail"),
            ("#55ff55", "Spindle"),
        ):
            painter.setPen(QColor(color))
            painter.drawText(x, y, label)
            x += 52
