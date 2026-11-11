"""Animated chest adapted from Xxoris190/chest-tracker (MIT, see LICENSE)."""

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from fortnite_chest_counter.detection import chest_types
from fortnite_chest_counter.gui.theme import STAGE_MOTIF, animations_enabled


@dataclass(frozen=True)
class ChestPalette:
    light: str
    dark: str
    metal: str
    clasp: str
    glow: str
    gem: str


PALETTES = {
    chest_types.NORMAL: ChestPalette("#c88438", "#67351e", "#f8c145", "#e5e3de", "#ffca60", "#e96afb"),
    chest_types.SPRITE: ChestPalette("#6d426e", "#241b38", "#a17b9e", "#615171", "#66dbff", "#ffa0f7"),
    chest_types.RARE: ChestPalette("#3ba6ef", "#143470", "#aabfce", "#e3ebf1", "#69ddff", "#6eebff"),
    chest_types.UNKNOWN: ChestPalette("#c9923d", "#65421e", "#7c858b", "#e8c57c", "#ffcf6f", "#ffc562"),
}


class ChestIllustration(QWidget):
    """A small dashboard illustration, repainted only during a confirmed opening."""

    def __init__(self, compact=False):
        super().__init__()
        self._compact = compact
        self.setFixedHeight(48 if compact else 158)
        if compact:
            self.setFixedWidth(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lift = 0.0
        self._opening = QVariantAnimation(self)
        self._animate = animations_enabled()
        self.kind = chest_types.NORMAL
        self._opening.setDuration(480)
        self._opening.setStartValue(0.0)
        self._opening.setKeyValueAt(0.36, 1.0)
        self._opening.setKeyValueAt(0.65, 1.0)
        self._opening.setEndValue(0.0)
        self._opening.valueChanged.connect(self._set_lift)

    def _set_lift(self, lift):
        self._lift = lift
        self.update()

    def set_kind(self, kind):
        kind = kind if kind in PALETTES else chest_types.UNKNOWN
        if kind != self.kind:
            self.kind = kind
            self.update()

    def reset_opening(self):
        self._opening.stop()
        if self._lift:
            self._set_lift(0.0)

    def celebrate(self):
        if self._animate and self.isVisible():
            self._opening.stop()
            self._opening.start()

    def _chest_box(self):
        max_width = 136 if self.kind == chest_types.SPRITE else 160
        return self.width() / 2, self.height() - (5 if self._compact else 12), min(self.width() * 0.68, max_width)

    def _body_top(self):
        _, bottom, width = self._chest_box()
        return bottom - width * 0.42

    def paintEvent(self, event):
        center, bottom, width = self._chest_box()
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            if not self._compact:
                painter.setBrush(QColor(STAGE_MOTIF))
                painter.drawPath(self._medallion(center, bottom - width * 0.37, width * 0.47))
            painter.setBrush(QColor(16, 9, 5, 145))
            painter.drawEllipse(QRectF(center - width * 0.59, bottom - width * 0.02, width * 1.18, width * 0.08))
            self._paint_chest(painter, center, bottom, width, self._lift)

    @staticmethod
    def _medallion(x, y, radius):
        path = QPainterPath()
        for step in range(96):
            angle = math.tau * step / 96
            edge = radius * (1.0 + 0.055 * math.cos(8 * angle))
            point = QPointF(x + math.cos(angle) * edge, y + math.sin(angle) * edge)
            if step:
                path.lineTo(point)
            else:
                path.moveTo(point)
        path.closeSubpath()
        return path

    def _paint_chest(self, p: QPainter, center: float, bottom: float, width: float, openness: float) -> None:
        colors = PALETTES[self.kind]
        half = width / 2
        body_top = self._body_top()
        lid_height = width * 0.33
        angle = min(openness, 1.2) * math.radians(112)
        lid_gap = lid_height * 0.72 * math.sin(min(angle, math.pi / 2))
        lid_bottom = body_top - lid_gap
        face = lid_height * math.cos(angle)
        outline = QPen(QColor("#2B1006"), width * 0.016)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # The inside of the chest shows behind the lifting lid.
        if openness > 0.02:
            p.setPen(outline)
            mouth = QLinearGradient(0, lid_bottom, 0, body_top)
            mouth.setColorAt(0, QColor(colors.dark))
            mouth.setColorAt(1, QColor(colors.glow))
            p.setBrush(QBrush(mouth))
            p.drawRect(QRectF(center - half * 0.96, lid_bottom, width * 0.96, body_top - lid_bottom + width * 0.02))

        # Lid.
        p.setPen(outline)
        if face >= 0:
            lid = QPainterPath()
            lid.moveTo(center - half, lid_bottom)
            lid.lineTo(center - half, lid_bottom - face * 0.55)
            lid.cubicTo(
                center - half, lid_bottom - face * 1.05,
                center + half, lid_bottom - face * 1.05,
                center + half, lid_bottom - face * 0.55,
            )
            lid.lineTo(center + half, lid_bottom)
            lid.closeSubpath()
            shade = QLinearGradient(0, lid_bottom - face, 0, lid_bottom)
            shade.setColorAt(0, QColor(colors.light))
            shade.setColorAt(1, QColor(colors.dark))
            p.setBrush(QBrush(shade))
            p.drawPath(lid)
            self._paint_bands(p, center, width, lid_bottom - face * 0.82, lid_bottom, colors.metal)
            self._paint_lid_details(p, center, lid_bottom - face * 0.76, width, colors)
        else:
            back = QRectF(center - half, lid_bottom + face, width, -face)
            p.setBrush(QColor(colors.dark))
            p.drawRoundedRect(back, width * 0.03, width * 0.03)
            if self.kind == chest_types.SPRITE:
                self._paint_lid_details(p, center, back.top(), width, colors)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(colors.metal))
            p.drawRect(QRectF(center - half, lid_bottom - width * 0.012, width, width * 0.024))

        # Body with plank lines and metal corners.
        p.setPen(outline)
        planks = QLinearGradient(0, body_top, 0, bottom)
        planks.setColorAt(0, QColor(colors.light))
        planks.setColorAt(1, QColor(colors.dark))
        p.setBrush(QBrush(planks))
        p.drawRoundedRect(QRectF(center - half, body_top, width, bottom - body_top), width * 0.02, width * 0.02)
        p.setPen(QPen(QColor(colors.dark), width * 0.008))
        for step in (0.34, 0.67):
            y = body_top + (bottom - body_top) * step
            p.drawLine(QPointF(center - half * 0.96, y), QPointF(center + half * 0.96, y))
        self._paint_bands(p, center, width, body_top, bottom, colors.metal)

        # Rim and clasp ride with the body, so the clasp stays put as the lid lifts.
        p.setPen(outline)
        p.setBrush(QColor(colors.metal))
        p.drawRect(QRectF(center - half, body_top - width * 0.012, width, width * 0.042))
        self._paint_clasp(p, center, body_top, width, colors)

    @staticmethod
    def _polygon(p, points):
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        path.closeSubpath()
        p.drawPath(path)

    def _paint_lid_details(self, p, center, top, width, colors):
        p.setBrush(QColor(colors.gem))
        if self.kind == chest_types.SPRITE:
            for offset, height in ((-0.14, 0.16), (0, 0.27), (0.14, 0.19)):
                x = center + offset * width
                self._polygon(p, [(x - width * 0.10, top), (x - width * 0.06, top - width * height * 0.7),
                                  (x + width * 0.03, top - width * height), (x + width * 0.10, top)])
        elif self.kind in (chest_types.NORMAL, chest_types.RARE):
            for offset in (-0.35, 0.35):
                p.drawEllipse(QPointF(center + offset * width, top + width * 0.055), width * 0.054, width * 0.046)

    def _paint_clasp(self, p, center, top, width, colors):
        p.save()
        p.translate(center, top)
        p.scale(width, width)
        p.setPen(QPen(QColor("#211923"), 0.014))
        p.setBrush(QColor(colors.clasp))
        if self.kind in (chest_types.NORMAL, chest_types.RARE):
            self._polygon(p, [(-0.15, -0.09), (0.15, -0.09), (0.18, 0.02), (0.12, 0.11),
                              (0.09, 0.19), (-0.09, 0.19), (-0.12, 0.11), (-0.18, 0.02)])
            p.setBrush(QColor(colors.gem))
            for x in (-0.077, 0.077):
                p.drawEllipse(QPointF(x, 0.012), 0.042, 0.039)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(colors.metal), 0.025))
            for side in (-1, 1):
                for index in range(3):
                    p.save()
                    p.translate(side * (0.23 + index * 0.09), 0.16 + index * 0.029)
                    p.rotate(side * 24)
                    p.drawRoundedRect(QRectF(-0.061, -0.024, 0.122, 0.048), 0.021, 0.021)
                    p.restore()
        elif self.kind == chest_types.SPRITE:
            self._polygon(p, [(0, -0.16), (0.15, -0.07), (0.12, 0.15), (0, 0.22),
                              (-0.12, 0.15), (-0.15, -0.07)])
            p.setBrush(QColor(colors.glow))
            self._polygon(p, [(0, -0.09), (0.045, 0.019), (0, 0.12), (-0.045, 0.019)])
        else:
            p.drawRoundedRect(QRectF(-0.10, -0.058, 0.20, 0.24), 0.025, 0.025)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#211923"))
            p.drawEllipse(QPointF(0, 0.029), 0.026, 0.026)
            p.drawRect(QRectF(-0.011, 0.03, 0.022, 0.064))
        p.restore()

    def _paint_bands(self, p: QPainter, center: float, width: float, top: float, bottom: float, metal: str) -> None:
        if bottom - top < 1:
            return
        p.setPen(QPen(QColor("#2B1006"), width * 0.008))
        p.setBrush(QColor(metal))
        for x in (-0.36, 0.36):
            p.drawRect(QRectF(center + (x - 0.04) * width, top, width * 0.08, bottom - top))
