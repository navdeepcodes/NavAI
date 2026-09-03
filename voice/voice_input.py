"""Voice input manager: record → transcribe → emit text."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QTimer

from logs.logger import logger
from voice.recorder import PushToTalkRecorder


class VoiceInputManager(QObject):
    """Manages the voice input lifecycle.

    States: idle → recording → transcribing → idle
    Polls recorder for auto-stop (silence/max duration) via QTimer.
    """

    state_changed = Signal(str)  # idle | recording | transcribing
    transcription_ready = Signal(str)
    auto_stopped = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._recorder = PushToTalkRecorder()
        self._state = "idle"
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._check_auto_stop)

    @property
    def state(self) -> str:
        return self._state

    def toggle(self) -> None:
        if self._state == "idle":
            self._start_recording()
        elif self._state == "recording":
            self._stop_and_transcribe()

    def start_recording(self) -> None:
        if self._state == "idle":
            self._start_recording()

    def stop_recording(self) -> None:
        if self._state == "recording":
            self._stop_and_transcribe()

    def _start_recording(self) -> None:
        if not self._recorder.start():
            self.error.emit(
                "Could not access the microphone. "
                "Check microphone permission in System Settings → "
                "Privacy & Security → Microphone."
            )
            return

        self._state = "recording"
        self.state_changed.emit("recording")
        self._poll_timer.start()

    def _check_auto_stop(self) -> None:
        if self._state != "recording":
            self._poll_timer.stop()
            return
        if self._recorder.should_auto_stop:
            self._poll_timer.stop()
            logger.info("Auto-stop triggered (silence or max duration)")
            self.auto_stopped.emit()
            self._stop_and_transcribe()

    def _stop_and_transcribe(self) -> None:
        self._poll_timer.stop()
        audio_path = self._recorder.stop()

        if audio_path is None:
            self._state = "idle"
            self.state_changed.emit("idle")
            self.error.emit("No speech detected. Try speaking louder.")
            return

        self._state = "transcribing"
        self.state_changed.emit("transcribing")

        from voice.transcriber import transcribe_async

        transcribe_async(
            audio_path,
            on_done=self._on_transcription_done,
            on_error=self._on_transcription_error,
        )

    def _on_transcription_done(self, text: str) -> None:
        self._state = "idle"
        self.state_changed.emit("idle")

        if text:
            self.transcription_ready.emit(text)
        else:
            self.error.emit("Couldn't understand the speech. Try again.")

    def _on_transcription_error(self, message: str) -> None:
        self._state = "idle"
        self.state_changed.emit("idle")
        self.error.emit(f"Transcription failed: {message}")
