"""The Qwen worker's control channel, without the model or any audio.

The worker used to read its next command only after fully generating the
current sentence. A barge-in therefore could not stop generation — it stopped
*playback*, but the machine kept producing a sentence nobody would hear, and
the reply the user actually wanted waited behind it. Generation now runs on
the main thread while a reader thread takes commands, so a `cancel` aborts the
current utterance between chunks and drops anything queued behind it.

The one thing that architecture must never get wrong is silencing the *next*
turn: a `cancel` for the sentence being interrupted must not also drop the
first sentence of what the user says next. That is pinned here with a real
run of the worker loop, driven through a pipe with a fake model — so it is
fast, silent, and needs no weights installed.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import numpy as np

import voice.providers.qwen_worker as worker


# ── fakes: a model that streams slowly, a pipe we control, captured output ──

class _FakeMx:
    """Just enough of mlx.core for the worker's chunk handling."""
    float32 = "f32"

    @staticmethod
    def array(x):
        class _W:
            def astype(self, _t):
                return x
        return _W()


class _FakeModel:
    """Streams fixed-size chunks with a gap between them, so a cancel arriving
    mid-generation has real chunks to interrupt."""

    def __init__(self, chunks: int = 60, chunk_samples: int = 1200,
                 gap: float = 0.03) -> None:
        self._chunks = chunks
        self._chunk_samples = chunk_samples
        self._gap = gap

    def generate(self, **_options):
        for _ in range(self._chunks):
            time.sleep(self._gap)

            class _Chunk:
                audio = np.zeros(self._chunk_samples, dtype=np.float32)
            yield _Chunk()


class _Pipe:
    """A stdin the test feeds one line at a time; close() ends iteration."""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()

    def feed(self, obj: dict) -> None:
        self._q.put(json.dumps(obj) + "\n")

    def close(self) -> None:
        self._q.put(_Pipe._END)

    _END = object()

    def __iter__(self):
        return self

    def __next__(self):
        item = self._q.get()
        if item is _Pipe._END:
            raise StopIteration
        return item


class _Harness:
    """Runs worker.main() with the model, mx and stdin all faked, capturing
    every event the worker emits."""

    def __init__(self, chunks: int = 60, gap: float = 0.03) -> None:
        self.events: list[dict] = []
        self._lock = threading.Lock()
        self._pipe = _Pipe()
        self._model = _FakeModel(chunks=chunks, gap=gap)
        self._thread: threading.Thread | None = None
        self._saved: dict = {}

    def _emit(self, obj: dict) -> None:
        with self._lock:
            self.events.append(obj)

    def __enter__(self) -> "_Harness":
        import types

        # Fake just the three imports worker.main() reaches for. numpy is real.
        fake_utils = types.ModuleType("mlx_audio.tts.utils")
        fake_utils.load_model = lambda _name: self._model
        fake_tts = types.ModuleType("mlx_audio.tts")
        fake_root = types.ModuleType("mlx_audio")
        fake_mlx = types.ModuleType("mlx")
        fake_mlx_core = _FakeMx()

        for name, mod in (
            ("mlx_audio", fake_root),
            ("mlx_audio.tts", fake_tts),
            ("mlx_audio.tts.utils", fake_utils),
            ("mlx", fake_mlx),
            ("mlx.core", fake_mlx_core),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[name] = mod

        self._saved["stdin"] = sys.stdin
        self._saved["emit"] = worker.emit
        sys.stdin = self._pipe
        worker.emit = self._emit

        self._thread = threading.Thread(target=worker.main, daemon=True)
        self._thread.start()
        self._await("ready", timeout=5)
        return self

    def __exit__(self, *_exc) -> None:
        self._pipe.feed({"cmd": "quit"})
        self._pipe.close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        sys.stdin = self._saved["stdin"]
        worker.emit = self._saved["emit"]
        for name in ("mlx.core", "mlx", "mlx_audio.tts.utils",
                     "mlx_audio.tts", "mlx_audio"):
            saved = self._saved.get(name)
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved

    def speak(self, request_id: int, text: str) -> None:
        self._pipe.feed({"cmd": "speak", "text": text, "id": request_id})

    def cancel(self) -> None:
        self._pipe.feed({"cmd": "cancel"})

    def _matching(self, event: str, request_id=None) -> list[dict]:
        with self._lock:
            return [e for e in self.events
                    if e.get("event") == event
                    and (request_id is None or e.get("id") == request_id)]

    def _await(self, event: str, request_id=None, timeout: float = 5) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits = self._matching(event, request_id)
            if hits:
                return hits[-1]
            time.sleep(0.02)
        raise AssertionError(f"never saw {event!r} for id={request_id}")

    def count(self, event: str, request_id=None) -> int:
        return len(self._matching(event, request_id))


LONG = ("I have finished going through all six regional spreadsheets and each "
        "one now has a total row at the bottom with the revenue for that region.")


def test_cancel_aborts_generation_in_flight():
    """A cancel stops the worker producing more audio, promptly, and reports
    the utterance as cancelled rather than done."""
    with _Harness() as h:
        h.speak(1, LONG)
        h._await("audio", request_id=1)          # generation is under way
        time.sleep(0.15)
        before = h.count("audio", request_id=1)

        h.cancel()
        h._await("cancelled", request_id=1, timeout=3)

        time.sleep(0.2)                           # let any stragglers land
        after = h.count("audio", request_id=1)
        assert after - before <= 2, (
            f"generation kept producing after cancel: {before} -> {after}")
        assert h.count("done", request_id=1) == 0, "a cancel must not report done"
    print("PASS: a cancel aborts in-flight generation promptly")


def test_a_new_utterance_after_cancel_is_not_dropped():
    """The property the epoch scheme exists for: cancelling the interrupted
    sentence must never silence the first sentence of the next turn."""
    with _Harness() as h:
        h.speak(1, LONG)
        h._await("audio", request_id=1)
        h.cancel()
        h._await("cancelled", request_id=1, timeout=3)

        # The very next thing the user says.
        h.speak(2, "Yes, what would you like instead?")
        h._await("audio", request_id=2, timeout=5)   # it MUST generate
        done = h._await("done", request_id=2, timeout=5)
        assert done["id"] == 2
        assert h.count("cancelled", request_id=2) == 0, (
            "the fresh utterance was wrongly dropped as cancelled")
    print("PASS: a new utterance after a cancel still speaks")


def test_queued_utterances_of_one_reply_generate_in_order():
    """Two sentences of the same reply both generate (overlap is the point of
    the worker holding a queue) — cancellation is the only thing that drops
    them."""
    with _Harness(chunks=6) as h:
        h.speak(1, "First sentence of the reply.")
        h.speak(2, "Second sentence of the reply.")
        h._await("done", request_id=1, timeout=5)
        h._await("done", request_id=2, timeout=5)
        assert h.count("cancelled") == 0
    print("PASS: queued sentences of one reply both generate")


def test_ctrl_epoch_never_cancels_a_newer_job():
    """The invariant in isolation: a cancel marks everything enqueued so far,
    and nothing enqueued afterward."""
    ctrl = worker.Ctrl()
    with ctrl.lock:
        ctrl.enq_seq += 1          # job 1
        ctrl.enq_seq += 1          # job 2
        ctrl.cancel_through = ctrl.enq_seq
    assert ctrl.cancelled(1) and ctrl.cancelled(2)
    with ctrl.lock:
        ctrl.enq_seq += 1          # job 3, a new turn
    assert not ctrl.cancelled(3), "a later job must survive an earlier cancel"
    print("PASS: the cancel epoch never reaches a newer job")


if __name__ == "__main__":
    test_ctrl_epoch_never_cancels_a_newer_job()
    test_cancel_aborts_generation_in_flight()
    test_a_new_utterance_after_cancel_is_not_dropped()
    test_queued_utterances_of_one_reply_generate_in_order()
    print("\nAll worker cancel tests passed.")
