"""How loud things are right now — your microphone, and Mike's voice.

The audio threads (the push-to-talk recorder and the Piper player) push the
level of each small block of sound they handle; the interface reads it to draw
the voice trace. So what you see moving is the real sound, not a loop: flat
when the room is quiet, lively when you speak, following Mike's voice as it
plays.

Levels are normalised to roughly 0..1 for ordinary speech (they can exceed 1
for a shout). Thread-safe; reading never blocks the audio thread for more than
a lock acquire.
"""
from __future__ import annotations

import collections
import threading
import time


class Meter:
    """A short ring buffer of (time, level) samples."""

    def __init__(self, keep_seconds: float = 3.0) -> None:
        self._samples: collections.deque[tuple[float, float]] = collections.deque(maxlen=2048)
        self._lock = threading.Lock()
        self._keep = keep_seconds

    def push(self, level: float, at: float | None = None) -> None:
        with self._lock:
            self._samples.append((time.monotonic() if at is None else at, max(0.0, float(level))))

    def push_block(self, levels: list[float], block_seconds: float) -> None:
        """Push the sub-levels of one audio block, spread across its duration
        (ending now), so a reader sampling by time sees them in order."""
        if not levels:
            return
        now = time.monotonic()
        step = block_seconds / len(levels)
        with self._lock:
            for i, lv in enumerate(levels):
                self._samples.append((now - block_seconds + (i + 1) * step, max(0.0, float(lv))))

    def level(self, window: float = 0.06) -> float:
        """The loudest recent level, or 0 if nothing has arrived lately."""
        cutoff = time.monotonic() - window
        with self._lock:
            recent = [lv for t, lv in self._samples if t >= cutoff]
        return max(recent) if recent else 0.0

    def last_update(self) -> float:
        with self._lock:
            return self._samples[-1][0] if self._samples else 0.0

    def live(self, within: float = 0.35) -> bool:
        """Has real audio been measured in the last moment?"""
        return time.monotonic() - self.last_update() <= within

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


#: Your microphone, while Mike is listening.
MIC = Meter()
#: Mike's own voice, while it's playing.
VOICE = Meter()


def rms_levels(samples, parts: int, scale: float) -> list[float]:
    """Split a block of float samples into `parts` and return each part's RMS
    divided by `scale` (the level that should read as ordinary speech)."""
    import numpy as np

    data = np.asarray(samples, dtype="float32").reshape(-1)
    if data.size == 0 or scale <= 0:
        return []
    chunks = np.array_split(data, max(1, parts))
    return [float(np.sqrt(np.mean(c * c))) / scale for c in chunks if c.size]
