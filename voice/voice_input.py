"""Voice input manager: record → transcribe → emit text."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, QTimer

from logs.logger import logger
from voice.recorder import RECORDING_DIR, PushToTalkRecorder

#: Quiet this long after speech and the words so far are transcribed, in the
#: background, while the recorder waits to be sure the person has finished.
#: Measured before: every command waited ~1s for the silence to confirm, then
#: ~2s for Whisper -- 3s from the last word to text. Transcribing during that
#: second, text is ready ~0.9s sooner; if they go on talking it's discarded.
SPECULATE_AFTER = 0.3
EARLY_FILE = RECORDING_DIR / "voice_input_early.wav"


class VoiceInputManager(QObject):
    """Manages the voice input lifecycle.

    States: idle → recording → transcribing → idle
    Polls recorder for auto-stop (silence/max duration) via QTimer.
    """

    state_changed = Signal(str)  # idle | recording | transcribing
    transcription_ready = Signal(str)
    auto_stopped = Signal()
    error = Signal(str)
    #: The mic closed with nothing said -- "Hey Mike" and then silence, or a
    #: false wake. Not an error: there's nothing to tell the person.
    nothing_heard = Signal()
    #: An early transcription finished that the turn is waiting for.
    _early_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._recorder = PushToTalkRecorder()
        self._state = "idle"
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._check_auto_stop)
        self._early: dict | None = None
        self._early_ready.connect(self._use_early)

    @property
    def state(self) -> str:
        return self._state

    def toggle(self) -> None:
        if self._state == "idle":
            self._start_recording()
        elif self._state == "recording":
            self._stop_and_transcribe()

    def start_recording(self, preroll=None, noise_floor: float | None = None,
                        no_speech_seconds: float | None = None) -> None:
        if self._state == "idle":
            self._start_recording(preroll, noise_floor, no_speech_seconds)

    def stop_recording(self) -> None:
        if self._state == "recording":
            self._stop_and_transcribe()

    def _start_recording(self, preroll=None, noise_floor: float | None = None,
                         no_speech_seconds: float | None = None) -> None:
        self._early = None
        if not self._recorder.start(preroll=preroll, noise_floor=noise_floor,
                                    no_speech_seconds=no_speech_seconds):
            self.error.emit(
                "Could not access the microphone. "
                "Check microphone permission in System Settings → "
                "Privacy & Security → Microphone."
            )
            return

        self._state = "recording"
        self.state_changed.emit("recording")
        self._poll_timer.start()

        # Load speech-to-text while the user is still talking, rather than
        # holding its memory all day in case they ever do.
        try:
            from voice.recognizer import get_recognizer
            warm = getattr(get_recognizer(), "warm", None)
            if warm is not None:
                warm()
        except Exception:
            logger.debug("Could not start loading speech-to-text.", exc_info=True)

    def _check_auto_stop(self) -> None:
        if self._state != "recording":
            self._poll_timer.stop()
            return
        rec = self._recorder
        if self._early is not None and self._early["epoch"] != rec.speech_epoch:
            self._early = None                       # they went on talking
        if (self._early is None and rec.heard_speech
                and rec.silence_seconds >= SPECULATE_AFTER and not rec.should_auto_stop):
            self._transcribe_early()
        if rec.should_auto_stop:
            self._poll_timer.stop()
            if not rec.heard_speech:
                rec.stop()
                self._early = None
                logger.info("Auto-stop with nothing said; back to idle.")
                self._state = "idle"
                self.state_changed.emit("idle")
                self.nothing_heard.emit()
                return
            logger.info("Auto-stop triggered (silence or max duration)")
            self.auto_stopped.emit()
            self._stop_and_transcribe()

    # -- early transcription -------------------------------------------
    def _transcribe_early(self) -> None:
        from voice.recognizer import RecognizerUnavailable, get_recognizer
        try:
            recognizer = get_recognizer()
            path = self._recorder.snapshot(EARLY_FILE)
        except (RecognizerUnavailable, OSError):
            return
        if path is None:
            return
        early = {"epoch": self._recorder.speech_epoch, "done": False, "wanted": False,
                 "text": None, "error": None, "lock": threading.Lock(), "full": None}
        self._early = early

        def finished(text, error) -> None:            # whisper's thread
            with early["lock"]:
                early.update(done=True, text=text, error=error)
                wanted = early["wanted"]
            if wanted:
                self._early_ready.emit(early)

        recognizer.transcribe_async(path, on_done=lambda t: finished(t, None),
                                    on_error=lambda e: finished(None, e))

    def _use_early(self, early: dict) -> None:
        """The pause was the end: the early transcription is the answer --
        unless it failed, and then the whole recording is transcribed."""
        if early.get("error") is None and early.get("text"):
            logger.info("Used the transcription started during the pause.")
            self._on_transcription_done(early["text"])
        elif early.get("full"):
            self._transcribe(early["full"])
        else:
            self._on_transcription_done(early.get("text") or "")

    # -- the end of recording ------------------------------------------
    def _stop_and_transcribe(self) -> None:
        self._poll_timer.stop()
        epoch = self._recorder.speech_epoch
        audio_path = self._recorder.stop()
        early, self._early = self._early, None

        if audio_path is None:
            self._state = "idle"
            self.state_changed.emit("idle")
            self.error.emit("No speech detected. Try speaking louder.")
            return

        self._state = "transcribing"
        self.state_changed.emit("transcribing")

        if early is not None and early["epoch"] == epoch:
            # Nothing said since the early transcription began: it covers it.
            with early["lock"]:
                early["full"] = audio_path
                ready = early["done"]
                early["wanted"] = not ready
            if ready:
                self._use_early(early)
            return
        self._transcribe(audio_path)

    def _transcribe(self, audio_path: str) -> None:
        from voice.recognizer import RecognizerUnavailable, get_recognizer

        try:
            recognizer = get_recognizer()
        except RecognizerUnavailable as exc:
            self._on_transcription_error(str(exc))
            return

        recognizer.transcribe_async(
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
