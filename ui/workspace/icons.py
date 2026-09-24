"""Mike's icons, drawn in code, and the one button that carries them.

Every glyph in the workspace comes from here: the same stroke weight, the same
rounded joins, the same optical size. Drawing them (rather than shipping stock
glyphs or relying on whatever a font has for "✕" or "▢") is what lets the
titlebar, the rail, the composer and the corner read as one product, in both
themes, at any display scale.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton

from ui.panel import style


def draw(p: QPainter, name: str, r: QRectF, col: QColor, width: float = 1.6) -> None:
    """Draw icon `name` inside rect `r` (square) with colour `col`."""
    pen = QPen(col)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    x, y, s = r.x(), r.y(), r.width()
    cx, cy = x + s / 2, y + s / 2

    def pt(fx: float, fy: float) -> QPointF:
        return QPointF(x + s * fx, y + s * fy)

    if name == "sidebar":
        p.drawRoundedRect(QRectF(x + s * 0.08, y + s * 0.16, s * 0.84, s * 0.68), s * 0.14, s * 0.14)
        p.drawLine(pt(0.38, 0.16), pt(0.38, 0.84))
    elif name == "compose":
        # a page with a pencil across its corner — "new chat"
        path = QPainterPath()
        path.moveTo(pt(0.50, 0.16))
        path.lineTo(pt(0.22, 0.16))
        path.quadTo(pt(0.12, 0.16), pt(0.12, 0.26))
        path.lineTo(pt(0.12, 0.78))
        path.quadTo(pt(0.12, 0.88), pt(0.22, 0.88))
        path.lineTo(pt(0.74, 0.88))
        path.quadTo(pt(0.84, 0.88), pt(0.84, 0.78))
        path.lineTo(pt(0.84, 0.52))
        p.drawPath(path)
        p.drawLine(pt(0.44, 0.58), pt(0.84, 0.18))
        p.drawLine(pt(0.44, 0.58), pt(0.42, 0.62))
    elif name == "plus":
        p.drawLine(pt(0.5, 0.2), pt(0.5, 0.8))
        p.drawLine(pt(0.2, 0.5), pt(0.8, 0.5))
    elif name == "close":
        p.drawLine(pt(0.27, 0.27), pt(0.73, 0.73))
        p.drawLine(pt(0.73, 0.27), pt(0.27, 0.73))
    elif name == "minimise":
        p.drawLine(pt(0.26, 0.5), pt(0.74, 0.5))
    elif name == "maximise":
        p.drawRoundedRect(QRectF(x + s * 0.26, y + s * 0.26, s * 0.48, s * 0.48), 1.5, 1.5)
    elif name == "restore":
        p.drawRoundedRect(QRectF(x + s * 0.24, y + s * 0.34, s * 0.42, s * 0.42), 1.5, 1.5)
        p.drawLine(pt(0.36, 0.24), pt(0.76, 0.24))
        p.drawLine(pt(0.76, 0.24), pt(0.76, 0.64))
    elif name == "gear":
        p.drawEllipse(QPointF(cx, cy), s * 0.13, s * 0.13)
        outer, inner = s * 0.40, s * 0.29
        path = QPainterPath()
        teeth = 8
        for i in range(teeth * 2):
            a = math.pi * 2 * i / (teeth * 2)
            rad = outer if i % 2 == 0 else inner
            a0 = a - math.pi / (teeth * 2) * 0.55
            a1 = a + math.pi / (teeth * 2) * 0.55
            p0 = QPointF(cx + rad * math.cos(a0), cy + rad * math.sin(a0))
            p1 = QPointF(cx + rad * math.cos(a1), cy + rad * math.sin(a1))
            if i == 0:
                path.moveTo(p0)
            else:
                path.lineTo(p0)
            path.lineTo(p1)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "mic":
        p.drawRoundedRect(QRectF(x + s * 0.37, y + s * 0.12, s * 0.26, s * 0.44), s * 0.13, s * 0.13)
        arc = QPainterPath()
        arc.moveTo(pt(0.24, 0.44))
        arc.arcTo(QRectF(x + s * 0.24, y + s * 0.18, s * 0.52, s * 0.52), 180, 180)
        p.drawPath(arc)
        p.drawLine(pt(0.5, 0.70), pt(0.5, 0.86))
    elif name == "attach":
        # a paperclip
        path = QPainterPath()
        path.moveTo(pt(0.66, 0.34))
        path.lineTo(pt(0.38, 0.62))
        path.quadTo(pt(0.30, 0.72), pt(0.40, 0.76))
        path.quadTo(pt(0.46, 0.78), pt(0.52, 0.72))
        path.lineTo(pt(0.80, 0.42))
        path.quadTo(pt(0.94, 0.26), pt(0.78, 0.16))
        path.quadTo(pt(0.66, 0.08), pt(0.54, 0.22))
        path.lineTo(pt(0.24, 0.54))
        path.quadTo(pt(0.06, 0.76), pt(0.26, 0.88))
        path.quadTo(pt(0.42, 0.96), pt(0.58, 0.80))
        path.lineTo(pt(0.80, 0.58))
        p.drawPath(path)
    elif name == "send":
        p.drawLine(pt(0.5, 0.80), pt(0.5, 0.22))
        p.drawLine(pt(0.28, 0.42), pt(0.5, 0.20))
        p.drawLine(pt(0.72, 0.42), pt(0.5, 0.20))
    elif name == "stop":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x + s * 0.30, y + s * 0.30, s * 0.40, s * 0.40), s * 0.07, s * 0.07)
    elif name == "check":
        path = QPainterPath()
        path.moveTo(pt(0.24, 0.52))
        path.lineTo(pt(0.43, 0.70))
        path.lineTo(pt(0.77, 0.32))
        p.drawPath(path)
    elif name == "chevron-down":
        path = QPainterPath()
        path.moveTo(pt(0.28, 0.40))
        path.lineTo(pt(0.5, 0.62))
        path.lineTo(pt(0.72, 0.40))
        p.drawPath(path)
    elif name == "chevron-right":
        path = QPainterPath()
        path.moveTo(pt(0.40, 0.28))
        path.lineTo(pt(0.62, 0.5))
        path.lineTo(pt(0.40, 0.72))
        p.drawPath(path)
    elif name == "trash":
        p.drawLine(pt(0.20, 0.28), pt(0.80, 0.28))
        p.drawLine(pt(0.40, 0.28), pt(0.42, 0.16))
        p.drawLine(pt(0.42, 0.16), pt(0.58, 0.16))
        p.drawLine(pt(0.58, 0.16), pt(0.60, 0.28))
        path = QPainterPath()
        path.moveTo(pt(0.27, 0.28))
        path.lineTo(pt(0.31, 0.82))
        path.quadTo(pt(0.32, 0.88), pt(0.38, 0.88))
        path.lineTo(pt(0.62, 0.88))
        path.quadTo(pt(0.68, 0.88), pt(0.69, 0.82))
        path.lineTo(pt(0.73, 0.28))
        p.drawPath(path)
    elif name == "copy":
        p.drawRoundedRect(QRectF(x + s * 0.34, y + s * 0.34, s * 0.46, s * 0.50), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(pt(0.62, 0.22))
        path.lineTo(pt(0.62, 0.20))
        path.quadTo(pt(0.62, 0.14), pt(0.56, 0.14))
        path.lineTo(pt(0.26, 0.14))
        path.quadTo(pt(0.20, 0.14), pt(0.20, 0.20))
        path.lineTo(pt(0.20, 0.60))
        path.quadTo(pt(0.20, 0.66), pt(0.26, 0.66))
        p.drawPath(path)
    elif name == "expand":
        p.drawLine(pt(0.58, 0.20), pt(0.80, 0.20))
        p.drawLine(pt(0.80, 0.20), pt(0.80, 0.42))
        p.drawLine(pt(0.80, 0.20), pt(0.56, 0.44))
        p.drawLine(pt(0.20, 0.58), pt(0.20, 0.80))
        p.drawLine(pt(0.20, 0.80), pt(0.42, 0.80))
        p.drawLine(pt(0.20, 0.80), pt(0.44, 0.56))
    elif name == "doc":
        path = QPainterPath()
        path.moveTo(pt(0.58, 0.12))
        path.lineTo(pt(0.28, 0.12))
        path.quadTo(pt(0.20, 0.12), pt(0.20, 0.20))
        path.lineTo(pt(0.20, 0.80))
        path.quadTo(pt(0.20, 0.88), pt(0.28, 0.88))
        path.lineTo(pt(0.72, 0.88))
        path.quadTo(pt(0.80, 0.88), pt(0.80, 0.80))
        path.lineTo(pt(0.80, 0.34))
        path.lineTo(pt(0.58, 0.12))
        path.lineTo(pt(0.58, 0.34))
        path.lineTo(pt(0.80, 0.34))
        p.drawPath(path)
        p.drawLine(pt(0.34, 0.54), pt(0.66, 0.54))
        p.drawLine(pt(0.34, 0.68), pt(0.58, 0.68))
    elif name == "sigma":
        path = QPainterPath()
        path.moveTo(pt(0.74, 0.20))
        path.lineTo(pt(0.28, 0.20))
        path.lineTo(pt(0.54, 0.50))
        path.lineTo(pt(0.28, 0.80))
        path.lineTo(pt(0.74, 0.80))
        p.drawPath(path)
    elif name == "code":
        path = QPainterPath()
        path.moveTo(pt(0.36, 0.28))
        path.lineTo(pt(0.14, 0.50))
        path.lineTo(pt(0.36, 0.72))
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(pt(0.64, 0.28))
        path2.lineTo(pt(0.86, 0.50))
        path2.lineTo(pt(0.64, 0.72))
        p.drawPath(path2)
        p.drawLine(pt(0.56, 0.18), pt(0.44, 0.82))
    elif name == "cursor":
        # a pointer — Mike acting on the computer
        path = QPainterPath()
        path.moveTo(pt(0.26, 0.14))
        path.lineTo(pt(0.26, 0.78))
        path.lineTo(pt(0.42, 0.63))
        path.lineTo(pt(0.54, 0.88))
        path.lineTo(pt(0.64, 0.83))
        path.lineTo(pt(0.52, 0.59))
        path.lineTo(pt(0.74, 0.58))
        path.closeSubpath()
        p.drawPath(path)
    elif name == "speaker":
        path = QPainterPath()
        path.moveTo(pt(0.14, 0.40))
        path.lineTo(pt(0.30, 0.40))
        path.lineTo(pt(0.50, 0.22))
        path.lineTo(pt(0.50, 0.78))
        path.lineTo(pt(0.30, 0.60))
        path.lineTo(pt(0.14, 0.60))
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(x + s * 0.44, y + s * 0.32, s * 0.24, s * 0.36), -60 * 16, 120 * 16)
        p.drawArc(QRectF(x + s * 0.44, y + s * 0.18, s * 0.40, s * 0.64), -60 * 16, 120 * 16)
    elif name == "memory":
        star = QPainterPath()
        star.moveTo(cx, y + s * 0.10)
        star.lineTo(cx + s * 0.13, cy - s * 0.13)
        star.lineTo(x + s * 0.90, cy)
        star.lineTo(cx + s * 0.13, cy + s * 0.13)
        star.lineTo(cx, y + s * 0.90)
        star.lineTo(cx - s * 0.13, cy + s * 0.13)
        star.lineTo(x + s * 0.10, cy)
        star.lineTo(cx - s * 0.13, cy - s * 0.13)
        star.closeSubpath()
        p.drawPath(star)
    elif name == "shield":
        shield = QPainterPath()
        shield.moveTo(pt(0.5, 0.10))
        shield.lineTo(pt(0.82, 0.22))
        shield.lineTo(pt(0.82, 0.48))
        shield.quadTo(pt(0.80, 0.78), pt(0.5, 0.90))
        shield.quadTo(pt(0.20, 0.78), pt(0.18, 0.48))
        shield.lineTo(pt(0.18, 0.22))
        shield.closeSubpath()
        p.drawPath(shield)
    elif name == "activity":
        path = QPainterPath()
        path.moveTo(pt(0.10, 0.52))
        path.lineTo(pt(0.32, 0.52))
        path.lineTo(pt(0.42, 0.26))
        path.lineTo(pt(0.58, 0.78))
        path.lineTo(pt(0.68, 0.52))
        path.lineTo(pt(0.90, 0.52))
        p.drawPath(path)
    elif name == "info":
        p.drawEllipse(QRectF(x + s * 0.12, y + s * 0.12, s * 0.76, s * 0.76))
        p.drawLine(pt(0.5, 0.46), pt(0.5, 0.68))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(cx, y + s * 0.33), s * 0.045, s * 0.045)
    elif name == "user":
        p.drawEllipse(QRectF(x + s * 0.32, y + s * 0.14, s * 0.36, s * 0.36))
        arc = QPainterPath()
        arc.moveTo(pt(0.16, 0.88))
        arc.arcTo(QRectF(x + s * 0.16, y + s * 0.56, s * 0.68, s * 0.70), 180, -180)
        p.drawPath(arc)
    elif name == "palette":
        p.drawEllipse(QRectF(x + s * 0.12, y + s * 0.12, s * 0.76, s * 0.76))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        for fx, fy in ((0.36, 0.38), (0.56, 0.32), (0.66, 0.52)):
            p.drawEllipse(QPointF(x + s * fx, y + s * fy), s * 0.05, s * 0.05)
    elif name == "warning":
        tri = QPainterPath()
        tri.moveTo(pt(0.5, 0.14))
        tri.lineTo(pt(0.88, 0.82))
        tri.lineTo(pt(0.12, 0.82))
        tri.closeSubpath()
        p.drawPath(tri)
        p.drawLine(pt(0.5, 0.40), pt(0.5, 0.58))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(cx, y + s * 0.70), s * 0.045, s * 0.045)


class IconButton(QAbstractButton):
    """A square, borderless button showing one icon.

    variant "ghost": the icon in muted ink, a soft tile behind it on hover.
    variant "primary": a filled accent disc — the one action that matters.
    variant "danger-hover": ghost, but the hover tile turns red (window close).
    """

    def __init__(self, icon: str, tooltip: str = "", size: int = 32,
                 icon_size: int = 18, variant: str = "ghost", parent=None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._size = size
        self._icon_size = icon_size
        self._variant = variant
        self._hover = False
        self._tint: str | None = None
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)
            self.setAccessibleName(tooltip)

    def set_icon(self, icon: str) -> None:
        if icon != self._icon:
            self._icon = icon
            self.update()

    def set_variant(self, variant: str) -> None:
        if variant != self._variant:
            self._variant = variant
            self.update()

    def set_tint(self, colour: str | None) -> None:
        """Override the icon colour (e.g. the accent while listening)."""
        self._tint = colour
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(self._size, self._size)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        enabled = self.isEnabled()

        if self._variant == "primary":
            fill = QColor(style.accent() if enabled else style.HAIRLINE)
            if self._hover and enabled:
                fill = fill.lighter(108)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(QRectF(0.5, 0.5, w - 1, h - 1))
            ink = QColor("#17140F") if enabled else QColor(style.INK_MUTE)
        elif self._variant == "solid":
            # a filled ink disc — used for Stop, which must be unmistakable
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.INK))
            p.drawEllipse(QRectF(0.5, 0.5, w - 1, h - 1))
            ink = QColor(style.GROUND)
        else:
            if self._hover and enabled:
                tile = QColor(style.STOP) if self._variant == "danger-hover" else QColor(style.INK)
                if self._variant != "danger-hover":
                    tile.setAlpha(18)
                p.setPen(Qt.NoPen)
                p.setBrush(tile)
                p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)
            if self._variant == "danger-hover" and self._hover:
                ink = QColor("#FFFFFF")
            elif self._tint:
                ink = QColor(self._tint)
            elif not enabled:
                ink = QColor(style.INK_FAINT)
            else:
                ink = QColor(style.INK if self._hover else style.INK_MUTE)

        s = self._icon_size
        draw(p, self._icon, QRectF((w - s) / 2, (h - s) / 2, s, s), ink)
