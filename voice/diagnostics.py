"""What happened to each utterance, without recording what was said.

Voice problems are hard to reason about after the fact: an utterance is gone
the moment it finishes, and "it sounded wrong" is not something you can grep
for. This keeps a short in-memory record of the mechanics — which voice, how
long to first audio, whether it was interrupted, whether it fell back and why
— so a person can ask "what did the voice actually do" and get an answer.

Two deliberate limits. **The spoken text is never stored**, only its length,
because the content of someone's conversation is not diagnostic data. And
nothing leaves the machine: this is a ring buffer in memory, not telemetry.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

# Enough to cover a long conversation, small enough to be free.
HISTORY = 200


@dataclass
class Utterance:
    provider: str
    characters: int
    started_at: float = field(default_factory=time.time)
    first_audio_ms: int | None = None
    finished_after_ms: int | None = None
    interrupted: bool = False
    fell_back_to: str = ""
    failure: str = ""
    truncated: str = ""

    def summary(self) -> str:
        bits = [f"{self.provider}", f"{self.characters} chars"]
        if self.first_audio_ms is not None:
            bits.append(f"first audio {self.first_audio_ms} ms")
        if self.finished_after_ms is not None:
            bits.append(f"finished in {self.finished_after_ms} ms")
        if self.interrupted:
            bits.append("interrupted")
        if self.fell_back_to:
            bits.append(f"fell back to {self.fell_back_to}")
        if self.truncated:
            bits.append(f"truncated ({self.truncated})")
        if self.failure:
            bits.append(f"failed: {self.failure}")
        return " | ".join(bits)


_lock = threading.Lock()
_history: deque[Utterance] = deque(maxlen=HISTORY)


def begin(provider: str, text: str) -> Utterance:
    record = Utterance(provider=provider, characters=len(text or ""))
    with _lock:
        _history.append(record)
    return record


def recent(limit: int = 20) -> list[Utterance]:
    with _lock:
        return list(_history)[-limit:]


def summary() -> dict:
    """Counts a person would actually ask for."""
    with _lock:
        records = list(_history)
    if not records:
        return {"utterances": 0}

    latencies = [r.first_audio_ms for r in records if r.first_audio_ms is not None]
    by_provider: dict[str, int] = {}
    for r in records:
        by_provider[r.provider] = by_provider.get(r.provider, 0) + 1

    result = {
        "utterances": len(records),
        "by_provider": by_provider,
        "interrupted": sum(1 for r in records if r.interrupted),
        "fell_back": sum(1 for r in records if r.fell_back_to),
        "failed": sum(1 for r in records if r.failure),
        "truncated": sum(1 for r in records if r.truncated),
    }
    if latencies:
        ordered = sorted(latencies)
        result["first_audio_ms"] = {
            "min": ordered[0],
            "median": ordered[len(ordered) // 2],
            "max": ordered[-1],
        }
    return result


def clear() -> None:
    with _lock:
        _history.clear()
