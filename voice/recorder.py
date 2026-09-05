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

SILENCE_DURATION = 1.2
MIN_SPEECH_DURATION = 0.3
MAX_RECORDING = 30

# A fixed threshold can't work across rooms and microphones — measured on
# this machine, ambient room noise (0.0064 RMS mean) sits only ~25% below
# the old fixed 0.008 threshold, leaving almost no headroom before ordinary
# background noise reads as "speech". Instead, the first CALIBRATION_BLOCKS
# of every recording sample the real noise floor, and the speech threshold
# is set relative to that — so it adapts to whatever room/mic is actually
# in use instead of assuming one number fits everyone's hardware.
CALIBRATION_SECONDS = 0.3
THRESHOLD_MULTIPLIER = 2.5
THRESHOLD_FLOOR = 0.004  # absolute minimum, for a near-silent calibration

# Without an explicit blocksize, sounddevice's default 'high' latency mode
# hands back ~400ms chunks on this hardware (measured) instead of the ~100ms
# the timing constants above assume — so RMS_WINDOW was really smoothing over
# up to 3.2s of stale audio, not the ~800ms it looked like. A fixed blocksize
# makes the callback cadence, and therefore every duration above, actually
# mean what it says.
BLOCK_SIZE = 1600  # 100ms @ 16kHz
BLOCK_SECONDS = BLOCK_SIZE / SAMPLE_RATE
RMS_WINDOW = 3  # 300ms smoothing — enough to reject a single spike, still snappy
MIN_SPEECH_BLOCKS = max(1, round(MIN_SPEECH_DURATION / BLOCK_SECONDS))
CALIBRATION_BLOCKS = max(1, round(CALIBRATION_SECONDS / BLOCK_SECONDS))


class PushToTalkRecorder:

    def __init__(self) -> None:
        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

        self._speech_detected = False
        self._speech_blocks = 0
        self._silence_start: float | None = None
        self._record_start: float | None = None
        self._should_auto_stop = False
        self._calibration: list[float] = []
        self._speech_threshold: float | None = None
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
            self._speech_blocks = 0
            self._silence_start = None
            self._record_start = time.monotonic()
            self._should_auto_stop = False
            self._rms_history.clear()
            self._calibration.clear()
            self._speech_threshold = None

            try:
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=BLOCK_SIZE,
                    latency="low",
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._recording = True
                logger.info(
                    "Recording started (blocksize=%d, ~%.0fms/callback)",
                    BLOCK_SIZE, BLOCK_SECONDS * 1000,
                )
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

        # First: measure the real noise floor of whatever room and
        # microphone are actually in use, rather than assuming a single
        # fixed RMS value works everywhere. No detection decisions are made
        # on these opening blocks — they're audio for the recording either
        # way, just not yet used to decide speech vs. silence.
        if self._speech_threshold is None:
            self._calibration.append(rms)
            if len(self._calibration) < CALIBRATION_BLOCKS:
                return
            floor = sum(self._calibration) / len(self._calibration)
            self._speech_threshold = max(floor * THRESHOLD_MULTIPLIER, THRESHOLD_FLOOR)
            logger.info(
                "Mic calibrated: noise floor=%.4f -> speech threshold=%.4f",
                floor, self._speech_threshold,
            )
            return

        self._rms_history.append(rms)
        avg_rms = sum(self._rms_history) / len(self._rms_history)
        now = time.monotonic()

        if avg_rms >= self._speech_threshold:
            self._silence_start = None
            if not self._speech_detected:
                # Require sustained level above threshold before treating this
                # as real speech — a single pop or breath used to latch
                # `_speech_detected` permanently, which meant the very next
                # natural pause could look like the end of the sentence.
                self._speech_blocks += 1
                if self._speech_blocks >= MIN_SPEECH_BLOCKS:
                    self._speech_detected = True
        else:
            self._speech_blocks = 0
            if self._speech_detected:
                if self._silence_start is None:
                    self._silence_start = now
                elif now - self._silence_start >= SILENCE_DURATION:
                    logger.info("Auto-stop: silence after speech (%.1fs quiet)", SILENCE_DURATION)
                    self._should_auto_stop = True

        elapsed = now - self._record_start if self._record_start else 0
        if elapsed >= MAX_RECORDING:
            logger.info("Auto-stop: max duration reached (%ds)", MAX_RECORDING)
            self._should_auto_stop = True
