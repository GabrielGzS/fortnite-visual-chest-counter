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


def compact(n):
    """A chest count for an axis: 88, 1,166, 317K, 14.4M."""
    n = float(n)
    if n < 10_000:
        return f"{round(n):,}"
    if n < 1_000_000:
        return f"{n / 1000:.0f}K"
    return f"{n / 1_000_000:.1f}M"


class ProbabilityCurve(QWidget):
    """The chance of at least one drop against chests opened, from 0 toward 99.99% (v0.5.0 Predictions). Marks the 50%, 90% and 99%
    milestones, the "1 in N" point, and where you are in this cycle. It never suggests that a chest's own chance grows: the curve is the
    chance of at least one across all those chests."""

    def __init__(self, height=280):
        super().__init__()
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.points, self.end, self.p, self.odds, self.you, self.accent = [], 1, None, None, None, theme.ACCENT
        self.team_you, self.team_label = None, None

    def show_curve(self, p, odds, accent, you=None, team_you=None, team_label=None):
        """you: your actual position (normal-odds chests); team_you: a team scenario's modeled position, drawn as a ring."""
        from fortnite_chest_counter import predictions
        self.p, self.odds, self.accent, self.you, self.team_you, self.team_label = p, odds, accent, you, team_you, team_label
        self.points, self.end = predictions.curve(p)
        self.update()

    def paintEvent(self, event):
        from fortnite_chest_counter import predictions
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = QRectF(48, 14, max(self.width() - 66, 10), max(self.height() - 46, 10))
        painter.setFont(_font(8))
        for share in (0, 0.25, 0.5, 0.75, 1.0):                # chance grid
            y = plot.bottom() - plot.height() * share
            painter.setPen(QPen(QColor(theme.BORDER), 1, Qt.SolidLine if share == 0 else Qt.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(QRectF(0, y - 8, plot.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{round(share * 100)}%")
        for share in (0, 0.25, 0.5, 0.75, 1.0):                # chest axis
            x = plot.left() + plot.width() * share
            painter.drawText(QRectF(x - 40, plot.bottom() + 6, 80, 16), Qt.AlignHCenter | Qt.AlignTop, compact(self.end * share))
        if self.p is None or not self.points:
            return

        def x_of(chests):
            return plot.left() + plot.width() * min(chests, self.end) / self.end

        def y_of(chance):
            return plot.bottom() - plot.height() * chance

        accent = QColor(self.accent)
        path = QPainterPath(QPointF(x_of(0), y_of(0)))
        for chests, chance in self.points:
            path.lineTo(QPointF(x_of(chests), y_of(chance)))
        area = QPainterPath(path)
        area.lineTo(QPointF(plot.right(), plot.bottom()))
        area.closeSubpath()
        fill = QColor(accent)
        fill.setAlphaF(0.12)
        painter.fillPath(area, fill)
        painter.setPen(QPen(accent, 2.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        for index, milestone in enumerate((0.5, 0.9, 0.99)):   # milestones: dashed drop lines, labels along the bottom
            chests = predictions.chests_to(milestone, self.p)
            x, y = x_of(chests), y_of(milestone)
            painter.setPen(QPen(QColor(theme.MUTED), 1, Qt.DashLine))
            painter.drawLine(QPointF(x, y), QPointF(x, plot.bottom()))
            painter.setPen(Qt.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(x, y), 3.5, 3.5)
            painter.setPen(QColor(theme.TEXT))
            painter.setFont(_font(8, bold=True))
            painter.drawText(QRectF(x + 4, plot.bottom() - 18 - 15 * index, 140, 14), Qt.AlignLeft | Qt.AlignVCenter,
                             f"{round(milestone * 100)}% at {compact(chests)}")
        odds_chance = predictions.chance(self.odds, self.p)    # "1 in N": N chests is not a guarantee
        x, y = x_of(self.odds), y_of(odds_chance)
        painter.setPen(QPen(QColor(theme.TEXT), 1.5))
        painter.setBrush(QColor(theme.BG))
        painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
        painter.setFont(_font(8, bold=True))
        painter.drawText(QRectF(x + 8, y - 22, 280, 14), Qt.AlignLeft | Qt.AlignVCenter,
                         f"{self.odds:,} chests (1 in {self.odds:,}): {predictions.percent(odds_chance)}")
        if self.team_you is not None and self.team_you > 0:    # a team scenario: a ring, never mistaken for you
            modeled = predictions.chance(self.team_you, self.p)
            x, y = x_of(self.team_you), y_of(modeled)
            painter.setPen(QPen(accent, 2.5))
            painter.setBrush(QColor(theme.BG))
            painter.drawEllipse(QPointF(x, y), 7, 7)
            left = x > plot.center().x()
            painter.setPen(accent)
            painter.setFont(_font(8, bold=True))
            painter.drawText(QRectF(x - 240 if left else x + 12, y - 22, 230, 14), (Qt.AlignRight if left else Qt.AlignLeft) | Qt.AlignVCenter,
                             f"{self.team_label} model: {compact(self.team_you)}{'+' if self.team_you > self.end else ''} \u00b7 "
                             f"{predictions.percent(modeled)}")
        if self.you is not None and self.you > 0:              # where you are in this cycle
            mine = predictions.chance(self.you, self.p)
            x, y = x_of(self.you), y_of(mine)
            painter.setPen(QPen(QColor(theme.BG), 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QPointF(x, y), 6, 6)
            text = f"You: {compact(self.you)}{'+' if self.you > self.end else ''} · {predictions.percent(mine)}"
            left = x > plot.center().x()
            below = mine >= 0.5                                # low on the chart, above the dot: clear of the milestone labels at the bottom
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(x - 230 if left else x + 10, y + 6 if below else y - 22, 220, 14),
                             (Qt.AlignRight if left else Qt.AlignLeft) | Qt.AlignVCenter, text)
