"""The mission, always in view — above the composer, and in the corner.

What someone is getting done should not live only in a chat that scrolls
away. The bar sits just above where you type: the goal, how far along it is
(counted from the work itself, not from Mike's say-so), and what's next. Click
it for every step and the evidence behind each tick. When a step completes —
because the document now shows it — it says so once, briefly, and settles.

The corner carries the same thing in one line, so it stays with you while
you're in Word and Mike is out of the way. Nothing here pops up, plays a sound
or asks for attention: it changes only when the work changes.

Painted from the theme's tokens on every paint, so light/dark switches need
nothing from the host.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ui.panel import style
from ui.workspace.icons import draw
from ui.workspace.steps import _Mark

#: How long "✓ Results — done" stays before the line returns to "Next: …".
FLASH_MS = 6000
#: How long a finished mission stays in view before it settles away.
SETTLE_MS = 9000


def _done_total(mission: dict) -> tuple[int, int]:
    steps = mission.get("steps", [])
    return sum(1 for s in steps if s["status"] == "done"), len(steps)


def _next(mission: dict) -> dict | None:
    return next((s for s in mission.get("steps", []) if s["status"] != "done"), None)


def _measure(step: dict) -> str:
    """'160/150 words' for a checked step, 'you said so' for a said one."""
    ev = step.get("evidence") or ""
    if step.get("section"):
        if "words" in ev:
            return ev.split(" in ")[0]
        return "not written yet" if step["status"] != "done" else ""
    return ev if step["status"] == "done" else ""


def _empty_mark(p: QPainter, r: QRectF) -> None:
    pen = QPen(QColor(style.INK_FAINT))
    pen.setWidthF(1.5)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(r.adjusted(2, 2, -2, -2))


def _ring(p: QPainter, r: QRectF, frac: float, complete: bool) -> None:
    track = QColor(style.INK)
    track.setAlpha(26)
    pen = QPen(track)
    pen.setWidthF(2.4)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(r)
    if frac > 0:
        arc = QPen(QColor(style.GOOD) if complete else style.qaccent())
        arc.setWidthF(2.4)
        arc.setCapStyle(Qt.RoundCap)
        p.setPen(arc)
        p.drawArc(r, 90 * 16, -int(360 * 16 * min(1.0, frac)))


class MissionBar(QWidget):
    """The full window's view of the active mission."""

    drop_requested = Signal()

    PAD_X = 14
    PAD_Y = 10
    HEAD = 26
    TRACK = 10
    NEXT = 22
    STEP = 26
    FOOT = 28

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mission: dict | None = None
        self._expanded = False
        self._armed = False
        self._flash = ""
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.timeout.connect(self._disarm)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(lambda: self.set_mission(None))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Your mission — click to see every step")
        self.hide()

    # ── what the controller drives ────────────────────────
    def set_mission(self, mission: dict | None, newly_done: list[str] | None = None) -> None:
        self._mission = mission
        self._settle_timer.stop()
        if mission is None:
            self._expanded = False
            self._disarm()
            self.hide()
            return
        if mission.get("status") == "done":
            # finished: shown as finished for a moment, then out of the way
            self._flash = ""
            self._expanded = False
            self._settle_timer.start(SETTLE_MS)
        if newly_done:
            step = next((s for s in mission["steps"] if s["title"] == newly_done[-1]), None)
            measure = f" · {_measure(step)}" if step and _measure(step) else ""
            self._flash = f"{newly_done[-1]} — done{measure}"
            self._flash_timer.start(FLASH_MS)
        self.setFixedHeight(self._height())
        self.show()
        self.update()

    def mission(self) -> dict | None:
        return self._mission

    # ── geometry ──────────────────────────────────────────
    def _height(self) -> int:
        h = self.PAD_Y * 2 + self.HEAD + self.TRACK + self.NEXT
        if self._expanded and self._mission:
            h += 6 + self.STEP * len(self._mission["steps"]) + self.FOOT
        return h

    def _foot_rect(self) -> QRectF:
        return QRectF(self.PAD_X, self.height() - self.PAD_Y - self.FOOT, 220, self.FOOT)

    # ── interaction ───────────────────────────────────────
    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._mission is None:
            return
        pos = e.position()
        if self._expanded and self._foot_rect().contains(pos):
            if self._armed:
                self._disarm()
                self.drop_requested.emit()
            else:
                self._armed = True
                self._arm_timer.start(4000)
                self.update()
            return
        self._expanded = not self._expanded
        self._disarm()
        self.setFixedHeight(self._height())
        self.update()

    def _disarm(self) -> None:
        if self._armed:
            self._armed = False
            self.update()

    def _end_flash(self) -> None:
        self._flash = ""
        self.update()

    # ── paint ─────────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        m = self._mission
        if m is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        body = QPainterPath()
        body.addRoundedRect(QRectF(0.5, 0.5, w - 1, self.height() - 1), 12, 12)
        p.fillPath(body, QColor(style.GROUND_RAISED))
        p.setPen(QPen(QColor(style.HAIRLINE), 1))
        p.drawPath(body)

        done, total = _done_total(m)
        complete = total > 0 and done == total
        x, y = self.PAD_X, self.PAD_Y

        # header: ring · goal · due · count · chevron
        _ring(p, QRectF(x + 1, y + (self.HEAD - 16) / 2, 16, 16), done / total if total else 0, complete)
        right = f"{done} of {total}"
        p.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        fm = p.fontMetrics()
        rw = fm.horizontalAdvance(right)
        p.setPen(QColor(style.INK_MUTE))
        p.drawText(QRectF(w - self.PAD_X - 22 - rw, y, rw, self.HEAD), Qt.AlignVCenter | Qt.AlignRight, right)
        draw(p, "chevron-down" if self._expanded else "chevron-right",
             QRectF(w - self.PAD_X - 16, y + (self.HEAD - 16) / 2, 16, 16), QColor(style.INK_MUTE), 1.6)

        due = f"due {m['deadline']}" if m.get("deadline") else ""
        p.setFont(style.font(style.CAPTION))
        dw = p.fontMetrics().horizontalAdvance(due) + 12 if due else 0
        goal_w = int(w - x - 26 - rw - 34 - dw)
        p.setFont(style.font(style.BODY, QFont.Weight.DemiBold))
        p.setPen(QColor(style.INK))
        goal = p.fontMetrics().elidedText(m["goal"], Qt.ElideRight, goal_w)
        p.drawText(QRectF(x + 26, y, goal_w, self.HEAD), Qt.AlignVCenter | Qt.AlignLeft, goal)
        if due:
            gx = x + 26 + p.fontMetrics().horizontalAdvance(goal) + 10
            p.setFont(style.font(style.CAPTION))
            p.setPen(QColor(style.WARN if not complete else style.INK_MUTE))
            p.drawText(QRectF(gx, y, dw, self.HEAD), Qt.AlignVCenter | Qt.AlignLeft, due)
        y += self.HEAD

        # progress: counted from the work
        track = QRectF(x + 26, y + 3, w - x - 26 - self.PAD_X, 4)
        tcol = QColor(style.INK)
        tcol.setAlpha(22)
        p.setPen(Qt.NoPen)
        p.setBrush(tcol)
        p.drawRoundedRect(track, 2, 2)
        if total and done:
            fill = QRectF(track.x(), track.y(), track.width() * done / total, track.height())
            p.setBrush(QColor(style.GOOD) if complete else style.qaccent())
            p.drawRoundedRect(fill, 2, 2)
        y += self.TRACK

        # next — or the moment a step completed
        nxt = _next(m)
        p.setFont(style.font(style.SMALL))
        if self._flash:
            # the font's own tick reads as a square-root sign; paint one
            _Mark.paint(p, QRectF(x + 2, y + (self.NEXT - 14) / 2, 14, 14), "done", 0)
            p.setFont(style.font(style.SMALL))
            p.setPen(QColor(style.GOOD))
            line = self._flash
        elif m.get("status") == "done":
            _Mark.paint(p, QRectF(x + 2, y + (self.NEXT - 14) / 2, 14, 14), "done", 0)
            p.setFont(style.font(style.SMALL))
            p.setPen(QColor(style.GOOD))
            line = "Finished — every step is done."
        elif nxt is None:
            p.setPen(QColor(style.GOOD))
            line = "Everything on the list is done — ask Mike to wrap it up."
        else:
            p.setPen(QColor(style.INK_SOFT))
            measure = _measure(nxt)
            line = f"Next: {nxt['title']}" + (f"  ·  {measure}" if measure else "")
            if m.get("blocker"):
                line += f"  ·  blocked: {m['blocker']}"
        line = p.fontMetrics().elidedText(line, Qt.ElideRight, int(w - x - 26 - self.PAD_X))
        p.drawText(QRectF(x + 26, y, w - x - 26 - self.PAD_X, self.NEXT), Qt.AlignVCenter | Qt.AlignLeft, line)
        y += self.NEXT

        if not self._expanded:
            return
        y += 6
        for s in m["steps"]:
            r = QRectF(x + 1, y + (self.STEP - 16) / 2, 16, 16)
            if s["status"] == "done":
                _Mark.paint(p, r, "done", 0)
            elif s["status"] == "blocked":
                _Mark.paint(p, r, "waiting", 0)
            else:
                _empty_mark(p, r)
            measure = _measure(s)
            p.setFont(style.font(style.CAPTION))
            mw = p.fontMetrics().horizontalAdvance(measure) + 6 if measure else 0
            p.setPen(QColor(style.INK_MUTE))
            if measure:
                p.drawText(QRectF(w - self.PAD_X - mw, y, mw, self.STEP), Qt.AlignVCenter | Qt.AlignRight, measure)
            p.setFont(style.font(style.BODY))
            p.setPen(QColor(style.INK_MUTE if s["status"] == "done" else style.INK_SOFT))
            tw = int(w - x - 26 - self.PAD_X - mw - 8)
            p.drawText(QRectF(x + 26, y, tw, self.STEP), Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(s["title"], Qt.ElideRight, tw))
            y += self.STEP

        p.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        p.setPen(QColor(style.STOP if self._armed else style.INK_MUTE))
        p.drawText(self._foot_rect(), Qt.AlignVCenter | Qt.AlignLeft,
                   "Click again to stop tracking" if self._armed else "Stop tracking this")


class MissionLine(QWidget):
    """The corner's one quiet line about the active mission."""

    clicked = Signal()
    H = 40

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mission: dict | None = None
        self._flash = ""
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self.setFixedHeight(self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Open Mike to see the whole mission")
        self.hide()

    def set_mission(self, mission: dict | None, newly_done: list[str] | None = None) -> bool:
        """Returns whether visibility changed, so the corner can resize."""
        was = self.isVisible()
        self._mission = mission
        if newly_done:
            self._flash = f"{newly_done[-1]} — done"
            self._flash_timer.start(FLASH_MS)
        if mission is not None and mission.get("status") == "done":
            self._flash = "Finished — every step is done"
            self._flash_timer.stop()
            QTimer.singleShot(SETTLE_MS, lambda: self._settle(mission))
        self.setVisible(mission is not None)
        self.update()
        return was != self.isVisible()

    def _settle(self, mission: dict) -> None:
        if self._mission is mission:
            self._mission = None
            self._flash = ""
            self.hide()
            parent = self.window()
            if hasattr(parent, "_resize_to_content"):
                parent._resize_to_content()

    def _end_flash(self) -> None:
        self._flash = ""
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        m = self._mission
        if m is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        done, total = _done_total(m)
        complete = total > 0 and done == total
        _ring(p, QRectF(3, 4, 16, 16), done / total if total else 0, complete)

        count = f"{done}/{total}"
        p.setFont(style.font(style.CAPTION, QFont.Weight.Medium))
        cw = p.fontMetrics().horizontalAdvance(count)
        p.setPen(QColor(style.INK_MUTE))
        p.drawText(QRectF(w - cw - 2, 0, cw, 24), Qt.AlignVCenter | Qt.AlignRight, count)

        p.setFont(style.font(style.SMALL, QFont.Weight.DemiBold))
        p.setPen(QColor(style.INK))
        gw = int(w - 28 - cw - 10)
        p.drawText(QRectF(28, 0, gw, 24), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(m["goal"], Qt.ElideRight, gw))

        nxt = _next(m)
        if self._flash:
            _Mark.paint(p, QRectF(5, 24, 12, 12), "done", 0)
            p.setPen(QColor(style.GOOD))
            line = self._flash
        elif nxt is None:
            p.setPen(QColor(style.GOOD))
            line = "All done"
        else:
            p.setPen(QColor(style.INK_MUTE))
            measure = _measure(nxt)
            line = f"Next: {nxt['title']}" + (f" · {measure}" if measure else "")
        p.setFont(style.font(style.CAPTION))
        p.drawText(QRectF(28, 22, w - 30, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(line, Qt.ElideRight, int(w - 30)))
