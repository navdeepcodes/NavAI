"""Windows wake-word detection: an always-on 'Hey Mike' spotter.

macOS gets NSSpeechRecognizer, a purpose-built command-and-control recognizer.
Windows has no equivalent that fits this contract, and rather than pull in a
new keyword-spotting dependency (openWakeWord, Porcupine, Vosk — each its own
model download and licence), this reuses what Mike already ships for
speech-to-text: faster-whisper. A *tiny* Whisper model (tiny.en, ~75MB, the
smallest there is, not the medium.en the real transcriber uses) runs on a
short rolling window of microphone audio and is checked for the wake word.

Two things keep an always-on recogniser from being a CPU hog or a
false-positive machine:

  - An energy gate. Silence and faint room noise never reach Whisper at all —
    the RMS of the window is checked first, and a quiet room does effectively
    no work. This also stops Whisper from hallucinating words out of silence,
    which the tiny model does readily.
  - A cooldown. One "Hey Mike" spans several overlapping windows; without a
    refractory period it would fire two or three times. After a hit, the
    buffer is cleared and further hits are ignored for a few seconds.

suppress()/resume() release and re-open the microphone stream, mirroring the
macOS backend's stopListening/startListening, so while Mike is speaking (or
while the push-to-talk recorder wants the mic) this backend is not also holding
it and not hearing Mike say his own name.

Verified on the physical machine: tiny.en transcribes a ~2s window in a few
hundred milliseconds on CPU, and a spoken "Hey Mike" lands as text containing
"mike". Chosen and measured here, not added as a guessed dependency.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from logs.logger import logger
from voice.wake.base import WakeWordBackend

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 1600                       # 100ms @ 16kHz, matches the recorder
WINDOW_SECONDS = 2.0                    # how much recent audio each check sees
CHECK_INTERVAL = 0.7                    # how often a check runs, when there's speech
MIN_AUDIO_SECONDS = 0.5                 # don't transcribe less than this
ENERGY_FLOOR = 0.012                    # absolute minimum RMS to consider at all
SPEECH_MULTIPLIER = 2.2                 # how far above the room's noise floor speech must sit
NOISE_ADAPT = 0.08                      # how fast the noise-floor estimate follows the room
COOLDOWN_SECONDS = 3.0                  # refractory period after a detection

# Whisper's spellings of the name, as whole words. "mic" is deliberately left
# out — it turns up in ordinary speech ("mic check", "microphone") and would
# fire constantly; the cost of missing a mumbled "Mike" is far smaller than a
# wake word that goes off mid-conversation.
_WAKE_WORDS = {"mike", "myke", "mikey"}
_WORD_RE = re.compile(r"[a-z]+")


class WindowsWakeWord(WakeWordBackend):

    def __init__(self, on_wake: Callable[[], None]) -> None:
        self._on_wake = on_wake
        self._model = None
        self._stream: sd.InputStream | None = None
        self._buf: collections.deque[float] = collections.deque(
            maxlen=int(WINDOW_SECONDS * SAMPLE_RATE))
        self._buf_lock = threading.Lock()
        self._active = False
        self._suppressed = False
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._last_fire = 0.0
        # An estimate of the room's steady noise level, so the gate adapts to
        # the actual room instead of one fixed number. Speech has to sit a
        # clear margin above this to be worth transcribing — otherwise a fan,
        # a GPU under load, or ordinary room tone keeps the tiny model
        # transcribing every second and the machine warm for nothing.
        self._noise_floor = ENERGY_FLOOR

    # -- lifecycle ----------------------------------------------------
    def start(self) -> bool:
        if self._active:
            return True
        try:
            self._stop.clear()
            self._open_stream()
        except Exception as exc:
            logger.warning("Windows wake word could not open the microphone: %s", exc)
            self._close_stream()
            return False
        self._worker = threading.Thread(
            target=self._listen_loop, name="wake-whisper", daemon=True)
        self._worker.start()
        self._active = True
        logger.info("Wake word detector started (tiny Whisper, CPU)")
        return True

    def stop(self) -> None:
        self._stop.set()
        self._close_stream()
        # Let the worker finish its current window and exit, so a rapid
        # restart doesn't stack detached transcription threads. Bounded, since
        # the loop only ever blocks for one short transcription.
        worker, self._worker = self._worker, None
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        self._active = False
        self._suppressed = False
        logger.info("Wake word detector stopped")

    def suppress(self) -> None:
        """Release the mic while Mike speaks, so he doesn't hear his own name."""
        if self._active and not self._suppressed:
            self._suppressed = True
            self._close_stream()
            with self._buf_lock:
                self._buf.clear()

    def resume(self) -> None:
        if self._active and self._suppressed:
            self._suppressed = False
            try:
                self._open_stream()
            except Exception as exc:
                logger.warning("Wake word could not re-open the microphone: %s", exc)
                self._suppressed = True

    @property
    def is_active(self) -> bool:
        return self._active

    # -- audio --------------------------------------------------------
    def _open_stream(self) -> None:
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            blocksize=BLOCK_SIZE, latency="low", callback=self._on_audio)
        self._stream.start()

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _on_audio(self, indata, _frames, _time, _status) -> None:
        if self._suppressed:
            return
        with self._buf_lock:
            self._buf.extend(indata[:, 0].copy())

    # -- detection ----------------------------------------------------
    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info("Loading tiny Whisper for wake word (first use)...")
            self._model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        return self._model

    def _listen_loop(self) -> None:
        try:
            model = self._load_model()
        except Exception:
            logger.exception("Wake word: could not load the tiny Whisper model.")
            return

        calibrated = False
        while not self._stop.wait(CHECK_INTERVAL):
            if self._suppressed:
                calibrated = False        # re-measure the room after a pause
                continue
            with self._buf_lock:
                if len(self._buf) < int(MIN_AUDIO_SECONDS * SAMPLE_RATE):
                    continue
                audio = np.array(self._buf, dtype=np.float32)

            rms = float(np.sqrt(np.mean(audio ** 2)))

            # Adaptive energy gate. Speech has to rise a clear margin above the
            # room's own noise floor, so an always-on recogniser doesn't
            # transcribe every second in a room that is simply not silent — a
            # fan, the GPU under load, room tone. The first window calibrates
            # the floor directly, so a loud room is handled from the start
            # rather than after a slow climb; after that every window nudges
            # the estimate, loud ones only slightly (so a burst of speech
            # barely moves it) and quiet ones more (so the room settling is
            # tracked quickly). That "track from every window" is the fix for
            # the earlier gate, which only lowered the floor and so never
            # adapted to a room that stayed loud.
            if not calibrated:
                self._noise_floor = max(ENERGY_FLOOR, rms)
                calibrated = True
                continue
            gate = max(ENERGY_FLOOR, self._noise_floor * SPEECH_MULTIPLIER)
            adapt = NOISE_ADAPT if rms < gate else NOISE_ADAPT * 0.3
            self._noise_floor = (1 - adapt) * self._noise_floor + adapt * rms
            if rms < gate:
                continue

            try:
                segments, _info = model.transcribe(audio, beam_size=1, language="en")
                text = " ".join(seg.text for seg in segments).lower()
            except Exception:
                continue

            if self._is_wake(text):
                now = time.monotonic()
                if now - self._last_fire < COOLDOWN_SECONDS:
                    continue
                self._last_fire = now
                with self._buf_lock:
                    self._buf.clear()
                if not self._suppressed:
                    logger.info("Wake word detected in: %r", text.strip()[:60])
                    try:
                        self._on_wake()
                    except Exception:
                        logger.exception("Wake word callback failed.")

    @staticmethod
    def _is_wake(text: str) -> bool:
        return any(word in _WAKE_WORDS for word in _WORD_RE.findall(text))
