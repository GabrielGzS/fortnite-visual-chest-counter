"""
Small charts for the Analytics page (v0.4.0), drawn with QPainter: no chart library, so nothing is added to the package.

Two rules carried over from the statistics they show:
  * A day (or week) with no counting is never drawn as a zero. Bars are chests; a short tick on the baseline is a counted day with none (a known
    zero); a hollow ring is a day nobody counted.
  * Time that was not counted is never drawn as play: on the build-up line, the stretches the app was counting are shaded, so a flat line over
    an unshaded stretch reads as "not watched", not as "nothing found".
"""

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from fortnite_chest_counter.gui import theme

CHESTS, ZERO, NOT_COUNTED = "chests", "zero", "not_counted"


@dataclass(frozen=True)
class Bar:
    label: str                             # under the bar, shown for some bars only when space is short
    value: int
    status: str                            # CHESTS, ZERO or NOT_COUNTED
    tip: str = ""                          # shown on hover


def _font(size, bold=False):
    font = QFont("Segoe UI")
    font.setPointSizeF(size)
    font.setBold(bold)
    return font


class BarChart(QWidget):
    """Bars for days or weeks, oldest on the left."""

    def __init__(self, height=150):
        super().__init__()
        self.bars = []
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self._slots = []

    def set_bars(self, bars):
        self.bars = list(bars)
        self.update()

    def _plot(self):
        return QRectF(8, 18, max(self.width() - 16, 1), max(self.height() - 40, 1))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot()
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        self._slots = []
        if not self.bars:
            painter.setPen(QColor(theme.DIM))
            painter.setFont(_font(9))
            painter.drawText(plot, Qt.AlignCenter, "Nothing recorded yet")
            return
        top = max([bar.value for bar in self.bars] + [1])
        slot = plot.width() / len(self.bars)
        width = max(min(slot * 0.62, 34), 2)
        every = max(1, round(len(self.bars) / max(plot.width() / 56, 1)))       # labels at least ~56 px apart
        painter.setFont(_font(8))
        for index, bar in enumerate(self.bars):
            x = plot.left() + slot * index + (slot - width) / 2
            centre = x + width / 2
            self._slots.append((plot.left() + slot * index, plot.left() + slot * (index + 1), bar))
            if bar.status == CHESTS and bar.value > 0:
                height = max(plot.height() * bar.value / top, 2)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.APPROX))
                painter.drawRoundedRect(QRectF(x, plot.bottom() - height, width, height), 2, 2)
                if bar.value == top:
                    painter.setPen(QColor(theme.TEXT))
                    painter.drawText(QRectF(centre - 30, plot.bottom() - height - 16, 60, 14), Qt.AlignCenter, str(bar.value))
            elif bar.status == ZERO:
                painter.setPen(QPen(QColor(theme.MUTED), 2))
                painter.drawLine(QPointF(x, plot.bottom() - 2), QPointF(x + width, plot.bottom() - 2))
            else:
                painter.setPen(QPen(QColor(theme.DIM), 1.2))
                painter.setBrush(Qt.NoBrush)
                radius = min(width / 2, 4)
                painter.drawEllipse(QPointF(centre, plot.bottom() - radius - 2), radius, radius)
            if index % every == 0 or index == len(self.bars) - 1:
                painter.setPen(QColor(theme.MUTED))
                painter.drawText(QRectF(centre - 28, plot.bottom() + 4, 56, 16), Qt.AlignHCenter | Qt.AlignTop, bar.label)

    def bar_at(self, x):
        return next((bar for left, right, bar in self._slots if left <= x < right), None)

    def mouseMoveEvent(self, event):
        bar = self.bar_at(event.position().x())
        if bar is not None and bar.tip:
            QToolTip.showText(event.globalPosition().toPoint(), bar.tip, self)
        else:
            QToolTip.hideText()


class BuildUpChart(QWidget):
    """Recorded chests adding up over a stretch of real time, with the counted stretches shaded."""

    def __init__(self, height=150):
        super().__init__()
        self.points, self.counted, self.span, self.labels = [], [], 1.0, ("", "")
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_series(self, points, counted, span, labels):
        """points: [(seconds from the start, running total)]; counted: [(from, to)] in seconds; span: the whole stretch in seconds;
        labels: (left, right) texts under the axis."""
        self.points, self.counted, self.span, self.labels = list(points), list(counted), max(float(span), 1.0), labels
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = QRectF(8, 18, max(self.width() - 16, 1), max(self.height() - 40, 1))

        def x_of(seconds):
            return plot.left() + plot.width() * min(max(seconds / self.span, 0.0), 1.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.SURFACE_2))
        for start, end in self.counted:
            painter.drawRect(QRectF(x_of(start), plot.top(), max(x_of(end) - x_of(start), 2), plot.height()))
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        painter.setFont(_font(8))
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 4, plot.width() / 2, 16), Qt.AlignLeft | Qt.AlignTop, self.labels[0])
        painter.drawText(QRectF(plot.center().x(), plot.bottom() + 4, plot.width() / 2, 16), Qt.AlignRight | Qt.AlignTop, self.labels[1])
        if not self.points:
            painter.setPen(QColor(theme.DIM))
            painter.setFont(_font(9))
            painter.drawText(plot, Qt.AlignCenter, "No chests in this period")
            return
        top = max(max(total for _, total in self.points), 1)

        def y_of(total):
            return plot.bottom() - plot.height() * max(total, 0) / top

        path = QPainterPath(QPointF(x_of(0), y_of(0)))
        previous = 0
        for seconds, total in self.points:                 # steps: the total holds until the next chest
            path.lineTo(QPointF(x_of(seconds), y_of(previous)))
            path.lineTo(QPointF(x_of(seconds), y_of(total)))
            previous = total
        path.lineTo(QPointF(x_of(self.span), y_of(previous)))
        painter.setPen(QPen(QColor(theme.APPROX), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRectF(plot.right() - 80, plot.top() - 16, 80, 14), Qt.AlignRight, str(previous))
