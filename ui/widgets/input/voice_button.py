"""Microphone button with voice interaction states."""
from __future__ import annotations


from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from ui.theme import colors


class VoiceButton(QPushButton):

    clicked_voice = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("voice_btn")
        self.setFixedSize(32, 32)
        self.setCursor(self.cursor())
        self._state = "idle"
        self._pulse_on = True
        self._pulse_timer = QTimer()
        self._pulse_timer.setInterval(600)
        self._pulse_timer.timeout.connect(self._pulse)
        self._apply_idle()
        self.clicked.connect(self.clicked_voice.emit)

    def set_state(self, state: str) -> None:
        self._state = state
        self._pulse_timer.stop()

        if state == "idle":
            self._apply_idle()
        elif state == "recording":
            self._pulse_on = True
            self._pulse_timer.start()
            self._apply_recording()
        elif state == "transcribing":
            self._apply_transcribing()
        elif state == "speaking":
            self._apply_speaking()

    def _pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        if self._pulse_on:
            self._apply_recording()
        else:
            self.setStyleSheet(
                f"""
                QPushButton#voice_btn {{
                    background: {colors.SURFACE_ELEVATED};
                    border: none;
                    border-radius: 16px;
                    color: {colors.ERROR};
                    font-size: 14px;
                    font-weight: 700;
                }}
                """
            )

    def _apply_idle(self) -> None:
        # Painted in paintEvent — an emoji glyph renders in full colour and
        # looks out of place against the Home's restrained palette.
        self.setText("")
        self.setToolTip("Voice input (F6)")
        self.setEnabled(True)
        self.setStyleSheet(
            f"""
            QPushButton#voice_btn {{
                background: transparent;
                border: none;
                border-radius: 16px;
                color: {colors.TEXT_MUTED};
                font-size: 16px;
            }}
            QPushButton#voice_btn:hover {{
                background: {colors.SURFACE_ELEVATED};
                color: {colors.TEXT};
            }}
            """
        )

    def _apply_recording(self) -> None:
        self.setText("●")
        self.setToolTip("Listening... (click or F6 to stop)")
        self.setEnabled(True)
        self.setStyleSheet(
            f"""
            QPushButton#voice_btn {{
                background: #3A1A1A;
                border: none;
                border-radius: 16px;
                color: {colors.ERROR};
                font-size: 14px;
                font-weight: 700;
            }}
            """
        )

    def _apply_transcribing(self) -> None:
        self.setText("…")
        self.setToolTip("Transcribing...")
        self.setEnabled(False)
        self.setStyleSheet(
            f"""
            QPushButton#voice_btn {{
                background: {colors.SURFACE_ELEVATED};
                border: none;
                border-radius: 16px;
                color: {colors.TEXT_MUTED};
                font-size: 16px;
            }}
            """
        )

    def _apply_speaking(self) -> None:
        self.setText("")
        self.setToolTip("Mike is speaking (click to interrupt)")
        self.setEnabled(True)
        self.setStyleSheet(
            f"""
            QPushButton#voice_btn {{
                background: transparent;
                border: none;
                border-radius: 16px;
                color: {colors.ACCENT};
                font-size: 16px;
            }}
            QPushButton#voice_btn:hover {{
                background: {colors.SURFACE_ELEVATED};
            }}
            """
        )

    # ------------------------------------------------------------------
    # Glyphs
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:

        super().paintEvent(event)

        if self._state not in ("idle", "speaking"):
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        tone = QColor(colors.ACCENT if self._state == "speaking" else colors.TEXT_MUTED)

        if self._state == "idle":
            self._paint_mic(p, cx, cy, tone)
        else:
            self._paint_waves(p, cx, cy, tone)

        p.end()

    @staticmethod
    def _paint_mic(p, cx, cy, tone) -> None:

        pen = QPen(tone)
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # Capsule
        p.drawRoundedRect(QRectF(cx - 3.0, cy - 7.0, 6.0, 10.0), 3.0, 3.0)

        # Cradle + stem
        p.drawArc(QRectF(cx - 5.5, cy - 4.5, 11.0, 11.0), 200 * 16, 140 * 16)
        p.drawLine(int(cx), int(cy + 6), int(cx), int(cy + 8))

    @staticmethod
    def _paint_waves(p, cx, cy, tone) -> None:

        pen = QPen(tone)
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        for i, r in enumerate((3.5, 6.5, 9.5)):
            colour = QColor(tone)
            colour.setAlphaF(0.9 - i * 0.25)
            pen.setColor(colour)
            p.setPen(pen)
            p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), -50 * 16, 100 * 16)
