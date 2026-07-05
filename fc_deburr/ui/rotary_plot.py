from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RotaryPlotWidget(QWidget):
    """Displays solved B/C values without owning or recalculating them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document = None
        self.setMinimumHeight(180)

    def set_document(self, document):
        self._document = document
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111417"))
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._document is None or not self._document.b_values:
            painter.setPen(QColor("#9aa4ad"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No solved B/C path")
            return

        margin = 42.0
        width = max(1.0, self.width() - 2.0 * margin)
        height = max(1.0, self.height() - 2.0 * margin)
        values = self._document.b_values + self._document.c_values
        minimum = min(values)
        maximum = max(values)
        if maximum - minimum < 1.0e-9:
            minimum -= 1.0
            maximum += 1.0

        painter.setPen(QPen(QColor("#4a5259"), 1.0))
        painter.drawRect(int(margin), int(margin), int(width), int(height))
        painter.setPen(QColor("#d7dde3"))
        painter.drawText(8, int(margin + 4), "%.1f°" % maximum)
        painter.drawText(8, int(margin + height), "%.1f°" % minimum)
        painter.setPen(QColor("#ffd23f"))
        painter.drawText(int(margin), 22, "B")
        painter.setPen(QColor("#ff7f66"))
        painter.drawText(int(margin + 16), 22, "C")

        def point(index, value, count):
            x = margin + width * index / max(1, count - 1)
            y = margin + height * (maximum - value) / (maximum - minimum)
            return QPointF(x, y)

        for series, color in (
            (self._document.b_values, "#ffd23f"),
            (self._document.c_values, "#ff7f66"),
        ):
            painter.setPen(QPen(QColor(color), 1.8))
            for index in range(1, len(series)):
                painter.drawLine(
                    point(index - 1, series[index - 1], len(series)),
                    point(index, series[index], len(series)),
                )
