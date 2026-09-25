"""Your avatar, drawn the same everywhere: your photo in a circle, or the
initial of the name Mike calls you on the accent colour."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from ui.panel import style
from ui.workspace.icons import draw

_cache: dict[tuple[str, float], QPixmap] = {}


def _photo(path: Path | None) -> QPixmap | None:
    if path is None:
        return None
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return None
    pix = _cache.get(key)
    if pix is None:
        pix = QPixmap(str(path))
        if pix.isNull():
            return None
        _cache.clear()
        _cache[key] = pix
    return pix


def current() -> tuple[str, Path | None]:
    """(name, photo) for whoever is using Mike right now."""
    name = ""
    photo = None
    try:
        from config import preferences
        name = str(preferences.get("profile_name", "") or "").strip()
    except Exception:
        pass
    try:
        from account.manager import manager
        m = manager()
        if m.signed_in():
            name = m.display_name() or name
            photo = m.avatar_file()
    except Exception:
        pass
    return name, photo


def paint(p: QPainter, rect: QRectF, name: str, photo: Path | None) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    circle = QPainterPath()
    circle.addEllipse(rect)
    pix = _photo(photo)
    if pix is not None:
        p.setClipPath(circle)
        p.drawPixmap(rect.toRect(), pix)
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(style.qaccent())
        p.drawPath(circle)
        initial = (name[:1] or "").upper()
        if initial:
            p.setPen(QColor("#17140F"))
            p.setFont(style.font(max(11, int(rect.height() * 0.42)), QFont.Weight.DemiBold))
            p.drawText(rect, Qt.AlignCenter, initial)
        else:
            inset = rect.width() * 0.25
            draw(p, "user", rect.adjusted(inset, inset, -inset, -inset), QColor("#17140F"),
                 max(1.4, rect.width() / 20))
    p.restore()


class Avatar(QWidget):
    """A round avatar of a fixed size; clickable when `clicked` is connected."""

    clicked = Signal()

    def __init__(self, size: int = 64, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._hover = False

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        name, photo = current()
        r = QRectF(0, 0, self.width(), self.height())
        paint(p, r, name, photo)
        if self._hover and self.receivers(self.clicked) > 0:
            p.setRenderHint(QPainter.Antialiasing, True)
            veil = QColor(0, 0, 0, 90)
            p.setPen(Qt.NoPen)
            p.setBrush(veil)
            p.drawEllipse(r)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(style.font(style.MICRO, QFont.Weight.DemiBold))
            p.drawText(r, Qt.AlignCenter, "Change")
