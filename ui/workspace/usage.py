"""Today's Fast mode allowance, at a glance.

A small ring in the corner of Mike's window fills as the day's free allowance
is used. Clicking it opens a small card: how much is left, and when it resets.
Both read brain/fast_usage.py (the real cost of every call, as Cloudflare
reports it) and only appear while Fast mode is connected and on.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QLabel, QVBoxLayout, QWidget

from ui.panel import style

_START = 90 * 16          # Qt draws arcs from 3 o'clock, in 1/16 degrees: start at 12


def _tone(used: float) -> QColor:
    """Ink while there's plenty; warmer as it runs low, and red at the end."""
    if used >= 1.0:
        return QColor(style.STOP)
    if used >= 0.85:
        return QColor(style.WARN)
    return QColor(style.INK_SOFT)


def _paint_ring(p: QPainter, rect: QRectF, used: float, width: float) -> None:
    track = QColor(style.INK)
    track.setAlpha(34)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(track, width))
    p.drawEllipse(rect)
    if used <= 0.0:
        return
    arc = QPen(_tone(used), width)
    arc.setCapStyle(Qt.RoundCap)
    p.setPen(arc)
    p.drawArc(rect, _START, int(-360 * 16 * min(1.0, max(0.02, used))))


class UsageRing(QAbstractButton):
    """The corner ring. Fills clockwise as the allowance is used."""

    SIZE = 26

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.PointingHandCursor)
        self._used = 0.0
        self._card: UsageCard | None = None
        self.clicked.connect(self._open)
        self._timer = QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self.refresh)
        self.hide()

    def start(self) -> None:
        """Begin watching. The ring shows itself once Fast mode is on."""
        self._timer.start()
        self.refresh()

    @staticmethod
    def _wanted() -> bool:
        try:
            from brain.providers import workers_ai_provider as fast
            return fast.fast_mode_on()
        except Exception:
            return False

    def refresh(self) -> None:
        """Re-read the allowance; the ring is there only while Fast mode is."""
        wanted = self._wanted()
        if wanted != self.isVisible():
            self.setVisible(wanted)
        if not wanted:
            return
        from brain import fast_usage
        used = fast_usage.fraction()
        if abs(used - self._used) > 1e-4 or not self.toolTip():
            self._used = used
            self.update()
            self.setToolTip(f"Fast mode: {1 - used:.0%} of today's allowance left")
        if self._card is not None and self._card.isVisible():
            self._card.refresh()

    def _open(self) -> None:
        if self._card is None:
            self._card = UsageCard(self)
        self._card.refresh()
        self._card.adjustSize()
        below = self.mapToGlobal(QPoint(self.width(), self.height() + 8))
        self._card.move(below.x() - self._card.width(), below.y())
        self._card.show()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.underMouse():
            hover = QColor(style.INK)
            hover.setAlpha(16)
            p.setPen(Qt.NoPen)
            p.setBrush(hover)
            p.drawEllipse(QRectF(0, 0, self.width(), self.height()))
        s = float(self.SIZE - 12)
        rect = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        _paint_ring(p, rect, self._used, 2.4)

    def enterEvent(self, e) -> None:
        super().enterEvent(e)
        self.update()

    def leaveEvent(self, e) -> None:
        super().leaveEvent(e)
        self.update()


class _BigRing(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(92, 92)
        self.used = 0.0

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _paint_ring(p, QRectF(6, 6, self.width() - 12, self.height() - 12), self.used, 6.0)
        left = max(0.0, 1.0 - self.used)
        p.setPen(QColor(style.INK))
        p.setFont(style.font(22, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 0, self.width(), self.height() - 6), Qt.AlignCenter, f"{left:.0%}")
        p.setPen(QColor(style.INK_MUTE))
        p.setFont(style.font(style.CAPTION))
        p.drawText(QRectF(0, 22, self.width(), self.height()), Qt.AlignCenter, "left")


class UsageCard(QWidget):
    """The small window: the share left today, when it comes back, and what
    was used."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(232)
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 20, 20, 18)
        col.setSpacing(4)

        title = QLabel("Fast mode today")
        title.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        title.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        title.setAlignment(Qt.AlignHCenter)
        col.addWidget(title)
        col.addSpacing(8)

        self._ring = _BigRing()
        col.addWidget(self._ring, 0, Qt.AlignHCenter)
        col.addSpacing(10)

        self._resets = QLabel("")
        self._resets.setFont(style.font(style.BODY, QFont.Weight.Medium))
        self._resets.setStyleSheet(f"color:{style.INK};background:transparent;")
        self._resets.setAlignment(Qt.AlignHCenter)
        col.addWidget(self._resets)

        self._in = QLabel("")
        self._in.setFont(style.font(style.CAPTION))
        self._in.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        self._in.setAlignment(Qt.AlignHCenter)
        col.addWidget(self._in)
        col.addSpacing(10)

        self._used = QLabel("")
        self._used.setFont(style.font(style.CAPTION))
        self._used.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
        self._used.setAlignment(Qt.AlignHCenter)
        col.addWidget(self._used)

    def refresh(self) -> None:
        from brain import fast_usage
        used = fast_usage.fraction()
        self._ring.used = used
        self._ring.update()
        at = fast_usage.resets_at()
        self._resets.setText(f"Resets at {time.strftime('%I:%M %p', time.localtime(at)).lstrip('0')}")
        seconds = max(0, int(at - time.time()))
        hours, minutes = seconds // 3600, seconds % 3600 // 60
        self._in.setText(f"in {hours}h {minutes:02d}m" if hours else f"in {minutes}m")
        self._used.setText(f"{fast_usage.used():,.0f} of {fast_usage.DAILY_NEURONS:,} used")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 14, 14)
        p.fillPath(path, QColor(style.SURFACE))
        p.setPen(QPen(QColor(style.HAIRLINE), 1.0))
        p.drawPath(path)
