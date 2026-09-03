"""Live view of what Mike is doing right now.

Shows completed steps and the one currently running — nothing else. Agency
decides each action only after seeing the previous result, so there is no
truthful way to render steps that haven't been chosen yet.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.home import motion
from ui.theme import colors


class _Step(QFrame):
    """One row: a state glyph plus what Mike did."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("step")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)

        self._glyph = QLabel("●")
        self._glyph.setObjectName("step_glyph")
        self._glyph.setFixedWidth(14)
        self._glyph.setAlignment(Qt.AlignCenter)
        row.addWidget(self._glyph)

        self._label = QLabel(text)
        self._label.setObjectName("step_label")
        self._label.setWordWrap(False)
        self._label.setTextFormat(Qt.PlainText)
        row.addWidget(self._label, 1)

        self._done = False
        self._pulse_on = True
        self._pulse = QTimer(self)
        self._pulse.setInterval(560)
        self._pulse.timeout.connect(self._blink)

        self._style_running()

        if not motion.reduced_motion():
            self._pulse.start()

    def text(self) -> str:
        return self._label.text()

    def _blink(self) -> None:
        self._pulse_on = not self._pulse_on
        tone = colors.HOME_LIVE if self._pulse_on else colors.HOME_TEXT_MUTED
        self._glyph.setStyleSheet(
            f"color: {tone}; font-size: 11px; background: transparent; border: none;"
        )

    def _style_running(self) -> None:
        self._glyph.setText("●")
        self._glyph.setStyleSheet(
            f"color: {colors.HOME_LIVE}; font-size: 11px;"
            " background: transparent; border: none;"
        )
        self._label.setStyleSheet(
            f"color: {colors.HOME_TEXT}; font-size: 13px;"
            " background: transparent; border: none;"
        )

    def mark_done(self, success: bool = True) -> None:
        if self._done:
            return

        self._done = True
        self._pulse.stop()

        self._glyph.setText("✓" if success else "✕")
        tone = colors.HOME_SUCCESS if success else colors.HOME_ERROR
        self._glyph.setStyleSheet(
            f"color: {tone}; font-size: 11px;"
            " background: transparent; border: none;"
        )
        self._label.setStyleSheet(
            f"color: {colors.HOME_TEXT_SECONDARY}; font-size: 13px;"
            " background: transparent; border: none;"
        )


class ActivityPanel(QWidget):
    """Layer 3 — only visible while Mike is actually working."""

    stop_requested = Signal()

    MAX_VISIBLE = 6

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self._frame = QFrame()
        self._frame.setObjectName("activity")
        self._frame.setMinimumWidth(420)
        self._frame.setMaximumWidth(560)

        self._steps_layout = QVBoxLayout(self._frame)
        self._steps_layout.setContentsMargins(18, 14, 18, 14)
        self._steps_layout.setSpacing(2)

        root.addWidget(self._frame, 0, Qt.AlignHCenter)

        self._stop = QPushButton("Stop")
        self._stop.setObjectName("stop_btn")
        self._stop.setCursor(Qt.PointingHandCursor)
        self._stop.setFixedHeight(30)
        self._stop.clicked.connect(self.stop_requested.emit)
        root.addWidget(self._stop, 0, Qt.AlignHCenter)

        self._steps: list[_Step] = []
        self._overflow = 0

        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#activity {{
                background: {colors.HOME_SURFACE};
                border: 1px solid {colors.HOME_BORDER};
                border-radius: 14px;
            }}
            QLabel#more {{
                color: {colors.HOME_TEXT_MUTED};
                font-size: 12px;
                background: transparent;
                border: none;
                padding-left: 24px;
            }}
            QPushButton#stop_btn {{
                background: transparent;
                border: 1px solid {colors.HOME_BORDER_LIT};
                border-radius: 15px;
                color: {colors.HOME_TEXT_SECONDARY};
                font-size: 12px;
                padding: 0 20px;
            }}
            QPushButton#stop_btn:hover {{
                border-color: {colors.HOME_ERROR};
                color: {colors.HOME_ERROR};
            }}
            """
        )

    # ── API used by the controller ───────────────────────────

    def begin_step(self, description: str):
        """A tool started. Returns the row so it can be completed later."""

        step = _Step(description, self._frame)
        self._steps.append(step)
        self._steps_layout.addWidget(step)

        self._trim()
        return step

    def complete_step(self, step, success: bool = True) -> None:
        if step is not None:
            step.mark_done(success)

    def _trim(self) -> None:
        """Keep the panel compact — oldest finished rows collapse to a count."""

        while len(self._steps) > self.MAX_VISIBLE:
            oldest = self._steps.pop(0)
            self._steps_layout.removeWidget(oldest)
            oldest.deleteLater()
            self._overflow += 1

        if self._overflow:
            self._ensure_overflow_label()

    def _ensure_overflow_label(self) -> None:
        if not hasattr(self, "_more"):
            self._more = QLabel()
            self._more.setObjectName("more")
            self._steps_layout.insertWidget(0, self._more)

        self._more.setText(f"{self._overflow} earlier steps")

    def reset(self) -> None:
        for step in self._steps:
            self._steps_layout.removeWidget(step)
            step.deleteLater()

        self._steps.clear()
        self._overflow = 0

        if hasattr(self, "_more"):
            self._more.deleteLater()
            del self._more

    def step_count(self) -> int:
        return len(self._steps) + self._overflow
