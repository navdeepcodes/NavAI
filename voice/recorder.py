"""Push-to-talk audio recorder with silence detection."""
from __future__ import annotations

import collections
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from logs.logger import logger

SAMPLE_RATE = 16000
CHANNELS = 1
RECORDING_DIR = Path("audio/recordings")
RECORDING_FILE = RECORDING_DIR / "voice_input.wav"

SPEECH_RMS_THRESHOLD = 0.008
SILENCE_DURATION = 1.2
MIN_SPEECH_DURATION = 0.3
MAX_RECORDING = 30
RMS_WINDOW = 8


class PushToTalkRecorder:

    def __init__(self) -> None:
        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

        self._speech_detected = False
        self._silence_start: float | None = None
        self._record_start: float | None = None
        self._should_auto_stop = False
        self._rms_history: collections.deque[float] = collections.deque(maxlen=RMS_WINDOW)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def should_auto_stop(self) -> bool:
        return self._should_auto_stop

    def start(self) -> bool:
        with self._lock:
            if self._recording:
                return False

            self._frames.clear()
            self._speech_detected = False
            self._silence_start = None
            self._record_start = time.monotonic()
            self._should_auto_stop = False
            self._rms_history.clear()

            try:
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._recording = True
                logger.info("Recording started")
                return True
            except Exception as exc:
                logger.exception("Failed to start recording: %s", exc)
                return False

    def stop(self) -> str | None:
        with self._lock:
            if not self._recording:
                return None

            self._recording = False

            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if not self._frames:
                logger.warning("No audio frames captured")
                return None

            audio = np.concatenate(self._frames, axis=0)
            self._frames.clear()

            peak = np.max(np.abs(audio))
            if peak < 0.005:
                logger.warning("Recording too quiet (peak=%.4f)", peak)
                return None

            sf.write(str(RECORDING_FILE), audio, SAMPLE_RATE)
            duration = len(audio) / SAMPLE_RATE
            logger.info(
                "Recording saved: %.1fs, peak=%.3f", duration, peak
            )
            return str(RECORDING_FILE)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Audio callback status: %s", status)
        if not self._recording:
            return

        self._frames.append(indata.copy())

        if self._should_auto_stop:
            return

        rms = float(np.sqrt(np.mean(indata ** 2)))
        self._rms_history.append(rms)
        avg_rms = sum(self._rms_history) / len(self._rms_history)
        now = time.monotonic()

        if avg_rms >= SPEECH_RMS_THRESHOLD:
            self._speech_detected = True
            self._silence_start = None
        elif self._speech_detected:
            if self._silence_start is None:
                self._silence_start = now
            elif now - self._silence_start >= SILENCE_DURATION:
                logger.info("Auto-stop: silence after speech (%.1fs quiet)", SILENCE_DURATION)
                self._should_auto_stop = True
                return

        elapsed = now - self._record_start if self._record_start else 0
        if elapsed >= MAX_RECORDING:
            logger.info("Auto-stop: max duration reached (%ds)", MAX_RECORDING)
            self._should_auto_stop = True
