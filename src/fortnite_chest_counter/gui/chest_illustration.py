"""Animated chest adapted from Xxoris190/chest-tracker (MIT, see LICENSE)."""

import ctypes
import math
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from fortnite_chest_counter.gui.theme import CHEST_EMBER as EMBER, CHEST_METAL as GOLD, STAGE_MOTIF


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
        animations = ctypes.c_int(1)
        if sys.platform == 'win32':
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(animations), 0)
        self._animate = bool(animations.value)
        self._opening.setDuration(480)
        self._opening.setStartValue(0.0)
        self._opening.setKeyValueAt(0.36, 1.0)
        self._opening.setKeyValueAt(0.65, 1.0)
        self._opening.setEndValue(0.0)
        self._opening.valueChanged.connect(self._set_lift)

    def _set_lift(self, lift):
        self._lift = lift
        self.update()

    def celebrate(self):
        if self._animate and self.isVisible():
            self._opening.stop()
            self._opening.start()

    def _chest_box(self):
        return self.width() / 2, self.height() - (5 if self._compact else 12), min(self.width() * 0.68, 160)

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
                painter.drawPath(self._medallion(center, bottom - width * 0.42, width * 0.53))
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
            mouth.setColorAt(0, QColor("#47210E"))
            mouth.setColorAt(1, QColor(GOLD))
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
            shade.setColorAt(0, QColor("#F08A55"))
            shade.setColorAt(1, QColor("#C4471F"))
            p.setBrush(QBrush(shade))
            p.drawPath(lid)
            self._paint_bands(p, center, width, lid_bottom - face * 0.82, lid_bottom)
        else:
            back = QRectF(center - half, lid_bottom + face, width, -face)
            p.setBrush(QColor("#6B2C14"))
            p.drawRoundedRect(back, width * 0.03, width * 0.03)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(GOLD))
            p.drawRect(QRectF(center - half, lid_bottom - width * 0.012, width, width * 0.024))

        # Body with plank lines and metal corners.
        p.setPen(outline)
        planks = QLinearGradient(0, body_top, 0, bottom)
        planks.setColorAt(0, QColor(EMBER))
        planks.setColorAt(1, QColor("#9E3414"))
        p.setBrush(QBrush(planks))
        p.drawRoundedRect(QRectF(center - half, body_top, width, bottom - body_top), width * 0.02, width * 0.02)
        p.setPen(QPen(QColor(70, 22, 8, 170), width * 0.008))
        for step in (0.34, 0.67):
            y = body_top + (bottom - body_top) * step
            p.drawLine(QPointF(center - half * 0.96, y), QPointF(center + half * 0.96, y))
        self._paint_bands(p, center, width, body_top, bottom)

        # Rim and clasp ride with the body, so the clasp stays put as the lid lifts.
        p.setPen(outline)
        p.setBrush(QColor(GOLD))
        p.drawRect(QRectF(center - half, body_top - width * 0.012, width, width * 0.042))
        clasp = QRectF(center - width * 0.075, body_top - width * 0.05, width * 0.15, width * 0.17)
        p.setBrush(QColor("#FFD978"))
        p.drawRoundedRect(clasp, width * 0.024, width * 0.024)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2B1006"))
        p.drawEllipse(clasp.center(), width * 0.021, width * 0.021)
        p.drawRect(QRectF(clasp.center().x() - width * 0.008, clasp.center().y(), width * 0.016, width * 0.05))

    def _paint_bands(self, p: QPainter, center: float, width: float, top: float, bottom: float) -> None:
        if bottom - top < 1:
            return
        p.setPen(QPen(QColor("#2B1006"), width * 0.008))
        p.setBrush(QColor(GOLD))
        for x in (-0.36, 0.36):
            p.drawRect(QRectF(center + (x - 0.04) * width, top, width * 0.08, bottom - top))
