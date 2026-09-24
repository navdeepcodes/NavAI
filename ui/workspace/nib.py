"""The nib — Mike's mark, and the pen that writes for him.

One silhouette, used everywhere: a fountain-pen nib angled exactly like a
mouse pointer, so it reads as both "writes" and "acts on your computer". The
shape lives here once, in unit coordinates with the writing tip at the
origin, so the app icon, the rail's mark, the corner, the handwriting pen and
the streaming cursor are all the very same drawing.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QTransform

#: The pointer angle: the nib leans back like a cursor (and like a pen held
#: in a right hand), tip up-left.
ANGLE = -38.0

_TIP_Y = -0.38


def _outline() -> QPainterPath:
    """The nib's body, tip at (0, -0.38), heel at y = 0.30 (unit height ~0.68)."""
    path = QPainterPath()
    path.moveTo(0, _TIP_Y)
    path.cubicTo(0.07, -0.25, 0.20, -0.08, 0.19, 0.08)
    path.lineTo(0.13, 0.30)
    path.lineTo(-0.13, 0.30)
    path.lineTo(-0.19, 0.08)
    path.cubicTo(-0.20, -0.08, -0.07, -0.25, 0, _TIP_Y)
    path.closeSubpath()
    return path


_K = 1000.0   # boolean ops flatten curves at the coordinates they're given


@lru_cache(maxsize=1)
def body() -> QPainterPath:
    """The nib with its breather hole and slit cut out, tip at the origin."""
    up = QTransform().scale(_K, _K)
    outline = up.map(_outline())
    hole = QPainterPath()
    hole.addEllipse(QPointF(0, 0.07 * _K), 0.045 * _K, 0.045 * _K)
    slit = QPainterPath()
    slit.addRect(QRectF(-0.011 * _K, -0.30 * _K, 0.022 * _K, 0.36 * _K))
    shape = outline.subtracted(hole).subtracted(slit)
    return QTransform().scale(1 / _K, 1 / _K).translate(0, -_TIP_Y * _K).map(shape)


@lru_cache(maxsize=1)
def band() -> QPainterPath:
    """The collar where the nib meets the pen, tip at the origin."""
    up = QTransform().scale(_K, _K)
    b = QPainterPath()
    b.addRect(QRectF(-0.13 * _K, 0.22 * _K, 0.26 * _K, 0.08 * _K))
    return QTransform().scale(1 / _K, 1 / _K).translate(0, -_TIP_Y * _K).map(
        b.intersected(up.map(_outline())))


def paint(p: QPainter, tip: QPointF, size: float, colour: QColor,
          collar: QColor | None = None, angle: float = ANGLE) -> None:
    """Draw the nib with its writing tip at `tip`, `size` px tall."""
    tr = QTransform()
    tr.translate(tip.x(), tip.y())
    tr.rotate(angle)
    tr.scale(size / 0.68, size / 0.68)
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(colour)
    p.drawPath(tr.map(body()))
    if collar is not None:
        p.setBrush(collar)
        p.drawPath(tr.map(band()))
    p.restore()


def paint_centred(p: QPainter, rect: QRectF, colour: QColor,
                  collar: QColor | None = None, angle: float = ANGLE,
                  scale: float = 0.82) -> None:
    """Draw the nib centred in `rect` (for marks and icons)."""
    size = min(rect.width(), rect.height()) * scale
    # The rotated nib's visual centre sits about 0.34 of its height from the
    # tip along its axis; place the tip so that centre lands on the rect's.
    import math
    a = math.radians(angle)
    along = size * 0.5
    dx, dy = -math.sin(a) * along, math.cos(a) * along
    tip = QPointF(rect.center().x() - dx, rect.center().y() - dy)
    paint(p, tip, size, colour, collar, angle)
