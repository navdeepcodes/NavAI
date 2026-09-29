"""The guide -- Mike's nib, showing where he's working.

While Mike works in other apps, his window steps aside and the nib does the
showing: it leaves the corner window, glides to the place he's about to act,
taps there with a small ripple as he clicks, and says in a few words what he's
doing ("Clicking Save", "Typing"). When the task is over it flies home.

It is a transparent layer over the whole screen that takes no clicks and
never takes focus, so it can't get in Mike's way or yours. Everything that
moves is worked out in screen pixels and drawn per monitor, so it lands on the
right spot at any display scaling.

computer/attention.py is where actions announce themselves (from Mike's worker
thread); this file is the interface's side of it.
"""
from __future__ import annotations

import ctypes
import math
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from logs.logger import logger
from ui.panel import style
from ui.workspace import nib as _nib

_FRAME_S = 0.016
_TRAIL_LIFE = 0.55
_RIPPLE_LIFE = 0.55
_LABEL_LIFE = 2.6
_NIB = 30.0                 # the nib's height, device-independent px


# ── monitors, in screen pixels ────────────────────────────────

class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", _Rect), ("work", _Rect),
                ("flags", wintypes.DWORD)]


def _monitor_at(x: float, y: float):
    """(handle, (left, top, right, bottom) in screen pixels, scale) of the
    monitor nearest a point, or None where that can't be asked."""
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        hmon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)
        info = _MonitorInfo()
        info.size = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            return None
        dpi_x, dpi_y = ctypes.c_uint(96), ctypes.c_uint(96)
        try:
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        except Exception:
            pass
        r = info.monitor
        return int(hmon), (r.left, r.top, r.right, r.bottom), max(1.0, dpi_x.value / 96.0)
    except Exception:
        return None


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


# ── the layer over one monitor ────────────────────────────────

class _Layer(QWidget):
    """A transparent, click-through window over one monitor."""

    def __init__(self, guide: "Guide", rect: tuple, scale: float) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self._guide = guide
        self.rect_px = rect
        self.scale = scale
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def cover(self) -> None:
        """Show over the whole monitor, on top, without touching focus."""
        left, top, right, bottom = self.rect_px
        # Qt's idea of the size first (in its own scaled pixels), so it and
        # the window agree; the exact placement in screen pixels follows.
        self.resize(round((right - left) / self.scale), round((bottom - top) / self.scale))
        self.show()
        try:
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
            hwnd = wintypes.HWND(int(self.winId()))
            GWL_EXSTYLE = -20
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # layered + click-through + never activated + not in Alt-Tab
            ex |= 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            # HWND_TOPMOST = -1; SWP_NOACTIVATE | SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, wintypes.HWND(-1), left, top, right - left, bottom - top,
                                0x0010 | 0x0040)
        except Exception:
            logger.debug("Couldn't place the guide layer.", exc_info=True)

    def paintEvent(self, _e) -> None:
        self._guide.paint(self)


# ── the guide ─────────────────────────────────────────────────

class Guide(QObject):
    """Animates the nib and owns the layers. Lives on the UI thread; actions
    reach it through `request`, from any thread."""

    #: Mike has started working outside his own window this turn (screen
    #: pixels of where, or -1 -1 when not known).
    outside_work = Signal(int, int)
    _asked = Signal(object)

    def __init__(self, home=None, parent=None) -> None:
        super().__init__(parent)
        #: () -> (x, y) in screen pixels: where the nib lives (the corner window).
        self._home = home
        self._layers: dict[int, _Layer] = {}
        self._layer: _Layer | None = None
        self._pos = QPointF(-1, -1)          # screen pixels
        self._from = QPointF()
        self._to = QPointF()
        self._bend = QPointF()
        self._t0 = 0.0
        self._dur = 0.0
        self._moving = False
        self._visible = False
        self._opacity = 0.0
        self._trail: list[tuple[float, float, float]] = []
        self._ripples: list[float] = []
        self._press = 0.0                     # when the last tap landed
        self._kind = ""
        self._label = ""
        self._label_at = 0.0
        self._last_ask = 0.0
        self._returning = False
        self._in_turn = False
        self._announced = False
        self._asked.connect(self._on_ask, Qt.AutoConnection)
        self._timer = QTimer(self)
        self._timer.setInterval(int(_FRAME_S * 1000))
        self._timer.timeout.connect(self._tick)

    # -- from the outside ---------------------------------------------------

    def begin_turn(self) -> None:
        """A new task: the window may step aside once, at the first action."""
        self._in_turn = True
        self._announced = False

    def end_turn(self) -> None:
        """The task is over: the nib goes home."""
        self._in_turn = False
        if self._visible:
            self._go_home()

    def request(self, kind: str, x, y, label: str) -> float:
        """From Mike's worker thread (or any): point the nib. Returns how long
        until it's there, so the action can wait for it."""
        box = {"kind": kind, "x": x, "y": y, "label": label, "eta": 0.0,
               "done": threading.Event()}
        self._asked.emit(box)
        if threading.current_thread() is not threading.main_thread():
            box["done"].wait(0.25)
        return float(box["eta"])

    # -- on the UI thread ---------------------------------------------------

    def _wanted(self) -> bool:
        try:
            from config import preferences
            return bool(preferences.get("guide_nib", True))
        except Exception:
            return True

    def _on_ask(self, box: dict) -> None:
        try:
            box["eta"] = self._point(box["kind"], box["x"], box["y"], box["label"])
        except Exception:
            logger.debug("The guide couldn't point.", exc_info=True)
        finally:
            box["done"].set()

    def _point(self, kind: str, x, y, label: str) -> float:
        if self._in_turn and not self._announced:
            self._announced = True
            self.outside_work.emit(-1 if x is None else x, -1 if y is None else y)
        if not self._wanted():
            return 0.0
        self._last_ask = time.monotonic()
        self._returning = False
        self._kind = kind
        if label:
            self._label, self._label_at = label, self._last_ask
        if x is None or y is None:
            if not self._visible:
                return 0.0
            self._tap(kind)
            return 0.05
        self._show_at(x, y)
        target = QPointF(float(x), float(y))
        distance = math.hypot(target.x() - self._pos.x(), target.y() - self._pos.y())
        scale = self._layer.scale if self._layer else 1.0
        self._from, self._to = QPointF(self._pos), target
        if style.reduced_motion() or distance < 3:
            self._dur = 0.0
        else:
            self._dur = min(0.75, 0.28 + (distance / scale) / 2600.0)
        # a gentle arc: the path bows to one side, more the further it goes
        dx, dy = target.x() - self._pos.x(), target.y() - self._pos.y()
        norm = math.hypot(dx, dy) or 1.0
        bow = min(90.0, distance * 0.12) * (1 if dx >= 0 else -1)
        self._bend = QPointF(-dy / norm * bow, dx / norm * bow)
        self._t0 = time.monotonic()
        self._moving = self._dur > 0
        if not self._moving:
            self._pos = QPointF(target)
            self._tap(kind)
        return self._dur + 0.04

    def _tap(self, kind: str) -> None:
        now = time.monotonic()
        self._press = now
        if kind in ("click", "window"):
            self._ripples.append(now)
            del self._ripples[:-3]

    def _home_point(self) -> QPointF:
        try:
            if self._home is not None:
                hx, hy = self._home()
                return QPointF(float(hx), float(hy))
        except Exception:
            pass
        return QPointF(80.0, 80.0)

    def _show_at(self, x: float, y: float) -> None:
        """Make sure a layer covers the monitor holding (x, y) and the nib is
        on it, appearing at home if it wasn't on screen."""
        found = _monitor_at(x, y)
        if found is None:
            return
        hmon, rect, scale = found
        layer = self._layers.get(hmon)
        if layer is None or layer.rect_px != rect or layer.scale != scale:
            layer = _Layer(self, rect, scale)
            self._layers[hmon] = layer
        if layer is not self._layer:
            if self._layer is not None:
                self._layer.hide()
            self._layer = layer
            layer.cover()
        elif not layer.isVisible():
            layer.cover()
        if not self._visible:
            self._visible = True
            self._pos = self._home_point()
            self._trail.clear()
        if not self._timer.isActive():
            self._timer.start()

    def _go_home(self) -> None:
        self._returning = True
        self._from, self._to = QPointF(self._pos), self._home_point()
        distance = math.hypot(self._to.x() - self._pos.x(), self._to.y() - self._pos.y())
        self._dur = 0.0 if style.reduced_motion() else min(0.8, 0.3 + distance / 2600.0)
        self._bend = QPointF(0, 0)
        self._t0 = time.monotonic()
        self._moving = self._dur > 0
        self._label = ""

    def _tick(self) -> None:
        now = time.monotonic()
        if self._moving:
            t = (now - self._t0) / self._dur if self._dur > 0 else 1.0
            e = _ease(t)
            bow = math.sin(math.pi * min(1.0, t))
            self._pos = QPointF(
                self._from.x() + (self._to.x() - self._from.x()) * e + self._bend.x() * bow,
                self._from.y() + (self._to.y() - self._from.y()) * e + self._bend.y() * bow)
            if not style.reduced_motion():
                self._trail.append((self._pos.x(), self._pos.y(), now))
            if t >= 1.0:
                self._moving = False
                self._pos = QPointF(self._to)
                if not self._returning:
                    self._tap(self._kind)
        self._trail = [p for p in self._trail if now - p[2] < _TRAIL_LIFE]
        self._ripples = [r for r in self._ripples if now - r < _RIPPLE_LIFE]

        # fade in while working, out once home (or when nothing has happened
        # for a long while)
        idle = now - self._last_ask > 60.0 and not self._in_turn
        goal = 0.0 if (idle or (self._returning and not self._moving)) else 1.0
        self._opacity += (goal - self._opacity) * 0.22
        if goal == 0.0 and self._opacity < 0.02:
            self._opacity = 0.0
            self._visible = self._returning = False
            self._timer.stop()
            if self._layer is not None:
                self._layer.hide()
            return
        if self._layer is not None:
            self._layer.update()

    # -- painting -----------------------------------------------------------

    def paint(self, layer: _Layer) -> None:
        if not self._visible or layer is not self._layer or self._opacity <= 0.01:
            return
        left, top = layer.rect_px[0], layer.rect_px[1]
        s = layer.scale

        def to_local(px: float, py: float) -> QPointF:
            return QPointF((px - left) / s, (py - top) / s)

        p = QPainter(layer)
        p.setRenderHint(QPainter.Antialiasing, True)
        now = time.monotonic()
        acc = QColor(style.accent())
        tip = to_local(self._pos.x(), self._pos.y())

        # the ink the nib leaves behind, drying as it fades
        for a, b in zip(self._trail, self._trail[1:]):
            age = (now - b[2]) / _TRAIL_LIFE
            c = QColor(acc)
            c.setAlphaF(max(0.0, 0.55 * (1.0 - age)) * self._opacity)
            pen = QPen(c, max(0.8, 3.2 * (1.0 - age)))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(to_local(a[0], a[1]), to_local(b[0], b[1]))

        # a soft light under the tip, and the ripple where a click lands
        halo = QRadialGradient(tip, 34)
        c0 = QColor(acc)
        c0.setAlphaF(0.22 * self._opacity)
        halo.setColorAt(0, c0)
        halo.setColorAt(1, QColor(acc.red(), acc.green(), acc.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(tip, 34, 34)
        for started in self._ripples:
            age = (now - started) / _RIPPLE_LIFE
            ring = QColor(acc)
            ring.setAlphaF(max(0.0, 0.75 * (1.0 - age)) * self._opacity)
            p.setPen(QPen(ring, 2.0))
            p.setBrush(Qt.NoBrush)
            radius = 5 + 26 * _ease(age)
            p.drawEllipse(tip, radius, radius)

        # the nib: dips into the page as a tap lands, writes a little while typing
        since = now - self._press
        dip = math.sin(math.pi * since / 0.18) if 0 <= since < 0.18 else 0.0
        wobble = 0.0
        jx = jy = 0.0
        if self._kind == "type" and not self._moving and not style.reduced_motion():
            jx = 1.3 * math.sin(now * 23.0)
            jy = 1.0 * math.sin(now * 29.0 + 1.1)
            wobble = 3.0 * math.sin(now * 11.0)
        p.setOpacity(self._opacity)
        _nib.paint(p, QPointF(tip.x() + jx + dip * 1.5, tip.y() + jy + dip * 2.0),
                   _NIB * (1.0 - 0.06 * dip), acc, acc.darker(210), _nib.ANGLE + wobble)

        # what he's doing, in a few words, beside the nib
        if self._label and now - self._label_at < _LABEL_LIFE:
            self._paint_label(p, layer, tip, now)
        p.end()

    def _paint_label(self, p: QPainter, layer: _Layer, tip: QPointF, now: float) -> None:
        age = now - self._label_at
        fade = min(1.0, age / 0.15) * min(1.0, (_LABEL_LIFE - age) / 0.4)
        font = style.font(style.CAPTION, QFont.Weight.Medium)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(self._label) + 22
        height = 26.0
        x, y = tip.x() + 20, tip.y() + 26
        w_local = layer.width()
        if x + width > w_local - 8:
            x = tip.x() - 20 - width
        y = min(max(8.0, y), layer.height() - height - 8)
        box = QRectF(x, y, width, height)
        path = QPainterPath()
        path.addRoundedRect(box, height / 2, height / 2)
        p.setOpacity(self._opacity * fade)
        fill = QColor(style.GROUND_SUNK)
        fill.setAlpha(232)
        p.fillPath(path, fill)
        p.setPen(QPen(QColor(style.HAIRLINE), 1.0))
        p.drawPath(path)
        p.setPen(QColor(style.INK))
        p.drawText(box, Qt.AlignCenter, self._label)
        p.setOpacity(1.0)
