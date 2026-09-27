"""Push-to-talk audio recorder with silence detection."""
from __future__ import annotations

import collections
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from hostplatform import storage
from logs.logger import logger

SAMPLE_RATE = 16000
CHANNELS = 1
# Used to be Path("audio/recordings"), relative to the working directory —
# the same class of bug as the log file and the OAuth token; see
# hostplatform/storage.py.
RECORDING_DIR = storage.recordings_dir()
RECORDING_FILE = RECORDING_DIR / "voice_input.wav"

SILENCE_DURATION = 1.2
MIN_SPEECH_DURATION = 0.3
MAX_RECORDING = 30
NO_SPEECH_SECONDS = 6

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
        self._speech_epoch = 0
        self._silence_start: float | None = None
        self._record_start: float | None = None
        self._should_auto_stop = False
        self._calibration: list[float] = []
        self._speech_threshold: float | None = None
        self._quietest: float | None = None
        self._rms_history: collections.deque[float] = collections.deque(maxlen=RMS_WINDOW)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def should_auto_stop(self) -> bool:
        return self._should_auto_stop

    @property
    def heard_speech(self) -> bool:
        return self._speech_detected

    @property
    def speech_epoch(self) -> int:
        """Changes whenever speech is heard: equal before and after means
        nothing was said in between."""
        return self._speech_epoch

    @property
    def silence_seconds(self) -> float:
        """How long it has been quiet since the person last spoke."""
        if not self._speech_detected or self._silence_start is None:
            return 0.0
        return time.monotonic() - self._silence_start

    def snapshot(self, path) -> str | None:
        """Everything recorded so far, written to `path`, while recording goes
        on -- so it can be transcribed during the pause that may end it."""
        frames = list(self._frames)
        if not frames:
            return None
        sf.write(str(path), np.concatenate(frames, axis=0), SAMPLE_RATE)
        return str(path)

    def start(self, preroll: np.ndarray | None = None,
              noise_floor: float | None = None,
              no_speech_seconds: float | None = None) -> bool:
        """Open the mic. `preroll` is audio already heard -- after "Hey Mike",
        the wake listener's last seconds, which hold the name and the start of
        the command -- and `noise_floor` the room's level measured before
        anyone spoke. Measured without them: "Hey Mike, open Notepad and
        write a shopping list" in one breath lost the command, and the first
        0.3s -- the person still talking -- was taken as the room's noise, so
        speech never rose above the threshold and recording never ended."""
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
            self._quietest = None
            self._no_speech_seconds = no_speech_seconds or NO_SPEECH_SECONDS
            if noise_floor:
                self._speech_threshold = max(noise_floor * THRESHOLD_MULTIPLIER, THRESHOLD_FLOOR)
                self._quietest = noise_floor
            if preroll is not None and len(preroll):
                self._take_preroll(np.asarray(preroll, dtype=np.float32).reshape(-1, 1))

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

    def _take_preroll(self, audio: np.ndarray) -> None:
        """Audio from before the mic opened, taken as if it had been recorded.

        It counts as speech in progress only if its end is speech: someone
        still talking when the wake word handed over ("Hey Mike, open..."),
        so the countdown to the end starts when they stop. A preroll that
        ends quiet is "Hey Mike." and a pause -- the command is still to
        come, and that pause must not end the recording.
        """
        self._frames.append(audio)
        blocks = [audio[i:i + BLOCK_SIZE] for i in range(0, len(audio) - BLOCK_SIZE + 1, BLOCK_SIZE)]
        levels = [float(np.sqrt(np.mean(b ** 2))) for b in blocks]
        if not levels:
            return
        quiet = float(np.percentile(levels, 20))
        self._quietest = min(self._quietest or quiet, quiet)
        if self._speech_threshold is None:
            self._speech_threshold = max(quiet * THRESHOLD_MULTIPLIER, THRESHOLD_FLOOR)
        tail = levels[-RMS_WINDOW:]
        self._rms_history.extend(tail)
        if sum(level >= self._speech_threshold for level in tail) >= min(2, len(tail)):
            self._speech_detected = True
        logger.info("Recording picked up %.1fs heard before the mic opened (%s).",
                    len(audio) / SAMPLE_RATE,
                    "still speaking" if self._speech_detected else "then quiet")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Audio callback status: %s", status)
        if not self._recording:
            return

        self._frames.append(indata.copy())

        rms = float(np.sqrt(np.mean(indata ** 2)))
        # Publish the live level for the voice trace, in 10ms slices so it
        # moves with syllables rather than stepping every 100ms. Scaled to
        # this room's own speech threshold once calibrated, so a quiet room
        # draws a flat line and ordinary speech fills the trace.
        try:
            from voice import levels
            ref = self._speech_threshold * 3.0 if self._speech_threshold else 0.03
            levels.MIC.push_block(levels.rms_levels(indata, 10, ref), BLOCK_SECONDS)
        except Exception:
            pass

        if self._should_auto_stop:
            return

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

        # The quietest stretch so far is the room's real floor. A threshold
        # set too high -- measured while someone was already talking -- comes
        # down to meet it, so speech is never above a line it can't reach.
        # It only ever moves down, and only on a full 300ms average: one
        # block of driver silence (0.0) must not drag it under the room tone.
        if len(self._rms_history) == RMS_WINDOW:
            self._quietest = avg_rms if self._quietest is None else min(self._quietest, avg_rms)
            self._speech_threshold = max(
                min(self._speech_threshold, self._quietest * THRESHOLD_MULTIPLIER),
                THRESHOLD_FLOOR)

        if avg_rms >= self._speech_threshold:
            self._silence_start = None
            self._speech_epoch += 1
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
        elif not self._speech_detected and elapsed >= self._no_speech_seconds:
            # Nobody spoke: "Hey Mike" and nothing more, or the button pressed
            # by mistake. Holding the mic open for the full 30s left Mike
            # "listening" to an empty room.
            logger.info("Auto-stop: no speech in %ss", self._no_speech_seconds)
            self._should_auto_stop = True
