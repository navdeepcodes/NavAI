"""The one-time welcome tour.

Shown after the very first install and never again. The panel's own starter
chips are good at "try something right now", but they cannot answer the
question a brand-new user actually has first, which is "what is this thing
and why is it on my computer". A paragraph in the panel can't either --
people skim it.

So: four short cards, one idea each, with something moving on every one.
The movement is not decoration. A local assistant asks for a lot of trust
(it can see your screen and change your files), and a surface that feels
alive and considered is what earns the few seconds needed to read why that
is safe.

Deliberately skippable from the first card, and deliberately never shown
twice -- a tour you cannot dismiss is a worse first impression than no tour.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui.panel import style

CARDS = (
    {
        "art": "presence",
        "title": "This is Mike.",
        "body": "He lives on this computer — not in a browser tab, not on "
                "someone's server. Everything he thinks happens here, and "
                "nothing you say leaves the machine.",
    },
    {
        "art": "doing",
        "title": "He can actually use your PC.",
        "body": "Open apps and websites, find and write files, read what's on "
                "your screen, fix code that won't run. Not instructions for "
                "doing it — he does it.",
    },
    {
        "art": "talking",
        "title": "Just say “Hey Mike.”",
        "body": "He's listening for his name, so you can talk to him hands-free "
                "from across the room. Rather type? Use the box at the bottom. "
                "Rather use a key? Ctrl+Shift+Space brings him to you from any "
                "other app, and F6 talks.",
    },
    {
        "art": "safe",
        "title": "He checks before he changes anything.",
        "body": "Anything that edits, deletes or sends gets shown to you "
                "first. Stop (or Esc) halts him mid-task at any time, and closing "
                "the window just tucks him into the corner.",
    },
)


class _Art(QWidget):
    """The moving illustration for a card.

    Each one animates a different idea, drawn rather than shipped as assets
    so it scales, themes, and costs nothing to load.
    """

    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._t = 0.0
        self.setFixedHeight(96)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // 30)

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self._t = 0.0
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._t += 1 / 30
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        accent = style.qaccent()
        ink = QColor(style.INK)
        mute = QColor(style.INK_FAINT)

        if self._kind == "presence":
            # The first thing Mike ever does: write "Hello", by hand, with the
            # nib that is his mark — then hold it, and write it again.
            from PySide6.QtCore import QPointF
            from ui.workspace import handwriting as hw
            if not hasattr(self, "_hello"):
                self._hello = hw.Script("Hello", seed=7) if hw.available() else None
            script = self._hello
            if script is None:
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawEllipse(int(cx - 9), int(cy - 9), 18, 18)
                return
            scale = 2.6
            pace = 1.15
            cycle = script.duration / pace + 2.2
            t = (self._t % cycle) * pace
            origin = QPointF(cx - script.width * scale / 2, cy + 20)
            tip = script.paint(p, origin, scale, t, QColor(style.INK), accent)
            _x, _y, down = script.pen_at(t)
            hw.paint_pen(p, tip, 40, accent, accent.darker(210), down)

        elif self._kind == "doing":
            # Three tasks completing in sequence, over and over: the point is
            # that things get done, not that a spinner is spinning.
            for i in range(3):
                x = cx - 96 + i * 96
                phase = (self._t * 0.75 - i * 0.45) % 3.0
                done = phase > 0.75
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(style.GROUND_SUNK))
                p.drawRoundedRect(int(x - 30), int(cy - 20), 60, 40, 9, 9)
                p.setBrush(accent if not done else QColor(style.GOOD))
                if done:
                    path = QPainterPath()
                    path.moveTo(x - 9, cy)
                    path.lineTo(x - 2, cy + 7)
                    path.lineTo(x + 10, cy - 7)
                    pen = p.pen()
                    p.setPen(QColor(style.GOOD))
                    stroke = p.pen()
                    stroke.setWidth(3)
                    p.setPen(stroke)
                    p.drawPath(path)
                    p.setPen(pen)
                else:
                    sweep = int((phase / 0.75) * 360 * 16)
                    p.setBrush(Qt.NoBrush)
                    pen = p.pen()
                    pen.setColor(accent)
                    pen.setWidth(3)
                    p.setPen(pen)
                    p.drawArc(int(x - 11), int(cy - 11), 22, 22, 90 * 16, -sweep)

        elif self._kind == "talking":
            # A voice waveform, alive rather than looping mechanically.
            p.setPen(Qt.NoPen)
            bars = 17
            for i in range(bars):
                x = cx - (bars * 11) / 2 + i * 11
                wave = math.sin(self._t * 3.4 + i * 0.55)
                h = 9 + abs(wave) * 30
                colour = QColor(accent if abs(wave) > 0.45 else mute)
                p.setBrush(colour)
                p.drawRoundedRect(int(x), int(cy - h / 2), 5, int(h), 2.5, 2.5)

        elif self._kind == "safe":
            # A request arriving and waiting for a yes: the pause is the point.
            pulse = 0.5 + 0.5 * math.sin(self._t * 2.2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(style.GROUND_SUNK))
            p.drawRoundedRect(int(cx - 110), int(cy - 26), 220, 52, 12, 12)
            p.setBrush(QColor(style.INK_FAINT))
            p.drawRoundedRect(int(cx - 92), int(cy - 9), 104, 7, 3, 3)
            p.drawRoundedRect(int(cx - 92), int(cy + 3), 68, 7, 3, 3)
            glow = QColor(style.GOOD)
            glow.setAlphaF(0.35 + 0.5 * pulse)
            p.setBrush(glow)
            p.drawRoundedRect(int(cx + 34), int(cy - 13), 62, 26, 9, 9)
            p.setPen(QColor(style.GROUND))
            p.setFont(style.font(style.CAPTION, QFont.Weight.DemiBold))
            p.drawText(int(cx + 34), int(cy - 13), 62, 26,
                       int(Qt.AlignCenter), "Allow")


class WelcomeWindow(QWidget):
    """The tour itself. Emits finished() when it closes, however it closes."""

    finished = Signal()

    SHADOW = 20
    WIDTH = 560
    HEIGHT = 470

    def __init__(self) -> None:
        super().__init__()
        self._index = 0
        self.setWindowTitle("Welcome to Mike")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._build()
        self._render()

    # ── painting the card itself ────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)
        for i in range(self.SHADOW, 0, -1):
            glow = QPainterPath()
            glow.addRoundedRect(
                self.rect().adjusted(self.SHADOW - i, self.SHADOW - i,
                                     -(self.SHADOW - i), -(self.SHADOW - i)),
                18 + i * 0.5, 18 + i * 0.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, max(1, int(9 - i * 0.4))))
            p.drawPath(glow)
        body = QPainterPath()
        body.addRoundedRect(rect, 18, 18)
        p.setBrush(QColor(style.GROUND))
        p.setPen(Qt.NoPen)
        p.drawPath(body)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW + 34, self.SHADOW + 26,
                                 self.SHADOW + 34, self.SHADOW + 22)
        outer.setSpacing(0)

        self._art = _Art(CARDS[0]["art"])
        outer.addWidget(self._art)
        outer.addSpacing(18)

        self._title = QLabel()
        self._title.setFont(style.font(24, QFont.Weight.DemiBold))
        self._title.setWordWrap(True)
        self._title.setStyleSheet(f"color:{style.INK};background:transparent;")
        outer.addWidget(self._title)
        outer.addSpacing(8)

        self._body = QLabel()
        self._body.setFont(style.font(style.BODY + 1))
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"color:{style.INK_SOFT};background:transparent;line-height:150%;")
        self._body.setMinimumHeight(86)
        outer.addWidget(self._body)
        outer.addStretch(1)

        bottom = QHBoxLayout()
        self._dots = _Dots(len(CARDS))
        bottom.addWidget(self._dots, 0, Qt.AlignVCenter)
        bottom.addStretch(1)

        self._skip = QPushButton("Skip")
        self._skip.setCursor(Qt.PointingHandCursor)
        self._skip.setFont(style.font(style.BODY, QFont.Weight.Medium))
        self._skip.setStyleSheet(
            f"QPushButton{{background:transparent;color:{style.INK_MUTE};"
            f"border:none;padding:9px 14px;}}"
            f"QPushButton:hover{{color:{style.INK};}}")
        self._skip.clicked.connect(self._close)
        bottom.addWidget(self._skip)

        self._next = QPushButton("Next")
        self._next.setCursor(Qt.PointingHandCursor)
        self._next.setFont(style.font(style.BODY, QFont.Weight.DemiBold))
        self._next.setStyleSheet(
            f"QPushButton{{background:{style.INK};color:{style.GROUND};"
            f"border:none;border-radius:9px;padding:10px 22px;}}"
            f"QPushButton:hover{{background:{style.accent()};}}")
        self._next.clicked.connect(self._advance)
        bottom.addWidget(self._next)
        outer.addLayout(bottom)

    # ── behaviour ───────────────────────────────────────────
    def _render(self) -> None:
        card = CARDS[self._index]
        self._art.set_kind(card["art"])
        self._title.setText(card["title"])
        self._body.setText(card["body"])
        self._dots.set_active(self._index)
        last = self._index == len(CARDS) - 1
        self._next.setText("Start using Mike" if last else "Next")
        self._skip.setVisible(not last)

        # Cross-fade rather than a hard cut, so moving between cards reads as
        # one surface changing its mind rather than four separate screens.
        for widget in (self._title, self._body):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity", widget)
            fade.setDuration(220)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            fade.start()

    def _advance(self) -> None:
        if self._index >= len(CARDS) - 1:
            self._close()
            return
        self._index += 1
        self._render()

    def _close(self) -> None:
        self._art.stop()
        self.close()
        self.finished.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._close()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right):
            self._advance()
            return
        super().keyPressEvent(event)

    # Frameless: move itself.
    def mousePressEvent(self, event) -> None:
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if getattr(self, "_drag", None) and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)


class _Dots(QWidget):
    """Which card you're on, and how many are left."""

    def __init__(self, count: int, parent=None) -> None:
        super().__init__(parent)
        self._count = count
        self._active = 0
        self.setFixedSize(count * 16, 16)

    def set_active(self, index: int) -> None:
        self._active = index
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        for i in range(self._count):
            on = i == self._active
            p.setBrush(style.qaccent() if on else QColor(style.INK_FAINT))
            size = 7 if on else 5
            y = (16 - size) / 2
            p.drawEllipse(int(i * 16), int(y), size, size)
