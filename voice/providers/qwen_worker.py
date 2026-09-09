"""The process that actually runs Qwen3-TTS. Not imported by Mike.

Run by voice/providers/qwen.py under a separate interpreter — the one with
mlx-audio installed — so Mike's own environment never takes on a
release-candidate dependency pin. Communication is one JSON object per line
on stdin, one per line on stdout.

It exists as a process rather than a thread for the same reason `say` does:
killing a process is the fastest, most complete way to stop speech, and it
cannot leave a half-finished generation attached to Mike.

Protocol
    in : {"cmd": "speak", "text": "...", "id": 7}
         {"cmd": "cancel"}                       abort in-flight + drop queued
         {"cmd": "ping"}
         {"cmd": "quit"}
    out: {"event": "ready"}                      once, after the model loads
         {"event": "audio", "id": 7, "path": "/tmp/....wav", "seconds": 1.9}
         {"event": "done", "id": 7, "seconds": 6.4}
         {"event": "cancelled", "id": 7, "seconds": 1.2}
         {"event": "error", "id": 7, "error": "..."}
         {"event": "truncated", "id": 7, "seconds": 21.0, "limit": 20.4}

Chunks are written as files and their paths reported, rather than piped as
bytes: the parent plays them with afplay, which keeps audio handling in the
parent where interruption already works.

Commands are read on a dedicated thread while generation runs on the main
thread, so a `cancel` (barge-in, or a new turn replacing this one) aborts the
current generation *between chunks* instead of after it finishes. Without that
split the worker read its next command only once the current sentence was
fully generated: an interrupted runaway kept the machine busy for seconds and
head-of-line-blocked the reply the user actually wanted to hear.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import tempfile
import threading
import time
import wave

MODEL = os.environ.get("MIKE_QWEN_TTS_MODEL",
                       "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit")
VOICE = os.environ.get("MIKE_QWEN_TTS_VOICE", "Ryan")

# Natural-language delivery control. Empty means the voice's own default.
# This is the model's `instruct` input: "speak warmly", "sound unhurried",
# "brisk and matter-of-fact". It shapes tone and pace without changing which
# voice is speaking, which is exactly the knob Mike wants — one assistant,
# adjustable manner.
INSTRUCT = os.environ.get("MIKE_QWEN_TTS_INSTRUCT", "").strip()

CHUNK_SECONDS = float(os.environ.get("MIKE_QWEN_TTS_CHUNK", "0.5"))
SAMPLE_RATE = 24000

# Measured: the model emits roughly 100 codec tokens per second of audio.
TOKENS_PER_SECOND = 100

# The runaway guard, configurable rather than buried. Defaults come from
# measurement — the slowest legitimate reading observed was 10.0 seconds for
# 118 characters — but the numbers are exposed because the right ceiling
# depends on the voice, the instruction and the machine, and a limit nobody
# can adjust is a limit that eventually clips someone's normal speech.
SECONDS_PER_CHARACTER = float(
    os.environ.get("MIKE_QWEN_TTS_SECONDS_PER_CHAR", 10.0 / 118.0))
CEILING_MULTIPLIER = float(os.environ.get("MIKE_QWEN_TTS_CEILING_FACTOR", "1.8"))
MINIMUM_CEILING = float(os.environ.get("MIKE_QWEN_TTS_MIN_SECONDS", "4.0"))
# An absolute cap regardless of text length. Nothing Mike says should run
# past this, however long the sentence.
ABSOLUTE_CEILING = float(os.environ.get("MIKE_QWEN_TTS_MAX_SECONDS", "60.0"))


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def duration_limit(text: str) -> float:
    """The longest this text could legitimately take to say.

    Derived from measurement, not guessed. Samantha reads at roughly 14
    characters per second; Qwen measured slower and variable, taking 6.2 to
    10.0 seconds for a 118-character line where Samantha took 5.4. So the
    ceiling is built from the slowest observed rate with generous headroom on
    top, plus a floor so that very short utterances are not clipped.

    The failure this guards against is not "slightly long". It is the
    measured case of 96 seconds of audio for a seven-second sentence — an
    order of magnitude out, not a fraction.
    """
    proportional = len(text) * SECONDS_PER_CHARACTER * CEILING_MULTIPLIER
    return min(ABSOLUTE_CEILING, max(MINIMUM_CEILING, proportional))


class Ctrl:
    """Shared cancellation state, addressed by a monotonic job number.

    A boolean "cancel" flag can't tell the sentence being interrupted apart
    from the first sentence of the *next* turn that arrives a millisecond
    later — clearing it races either way. So each `speak` gets an increasing
    `_seq`, a `cancel` records the highest seq seen so far in `cancel_through`,
    and a job is abandoned exactly when `cancel_through >= its seq`. A fresh
    utterance always has a higher seq than any prior cancel, so a stale cancel
    can never silence it, and no clearing is needed.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.enq_seq = 0
        self.cancel_through = 0
        self.quit = False

    def cancelled(self, seq: int) -> bool:
        with self.lock:
            return self.cancel_through >= seq


def _reader(work: "queue.Queue", ctrl: Ctrl) -> None:
    """Read commands off stdin so they can interrupt an in-flight generation.

    A `cancel` marks every job enqueued so far as abandoned and drops anything
    still queued, because a barge-in or a new turn abandons the whole reply,
    not just the sentence being spoken right now.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        cmd = msg.get("cmd")
        if cmd == "speak":
            with ctrl.lock:
                ctrl.enq_seq += 1
                msg["_seq"] = ctrl.enq_seq
            work.put(msg)
        elif cmd == "cancel":
            with ctrl.lock:
                ctrl.cancel_through = ctrl.enq_seq
            _drain(work)
        elif cmd == "ping":
            emit({"event": "pong"})
        elif cmd == "quit":
            with ctrl.lock:
                ctrl.cancel_through = ctrl.enq_seq
                ctrl.quit = True
            _drain(work)
            work.put(None)          # unblock the generation thread's get()
            return
    # stdin closed: parent is gone.
    with ctrl.lock:
        ctrl.cancel_through = ctrl.enq_seq
        ctrl.quit = True
    work.put(None)


def _drain(work: "queue.Queue") -> None:
    try:
        while True:
            work.get_nowait()
    except queue.Empty:
        pass


def _generate(model, mx, np, workdir: str, request_id: int, text: str,
              seq_start: int, job_seq: int, ctrl: Ctrl) -> int:
    """Generate one utterance, stopping promptly if it gets cancelled.

    Returns the new chunk sequence counter. Cancellation is checked before
    every chunk is written, so no audio past the interruption is ever emitted.
    """
    limit = duration_limit(text)
    deadline = time.monotonic() + max(20.0, limit * 3)
    produced = 0.0
    stopped = None
    seq = seq_start

    try:
        # Two limits that must agree. The duration ceiling below stops a
        # runaway; this stops generation hitting a token cap first and
        # cutting a normal sentence off mid-word — measured at ~100
        # tokens per second of audio, and the convenience wrapper's
        # default of 1200 truncated roughly a quarter of Mike-length
        # sentences at exactly 12.00 seconds. Derived from the same
        # ceiling so the two can never drift apart.
        options = {"text": text, "voice": VOICE, "verbose": False,
                   "stream": True, "streaming_interval": CHUNK_SECONDS,
                   "max_tokens": int(limit * TOKENS_PER_SECOND * 1.2)}
        if INSTRUCT:
            options["instruct"] = INSTRUCT

        for chunk in model.generate(**options):
            # Barge-in check, first: an abandoned utterance should stop
            # producing the instant the user takes over, not one chunk later.
            if ctrl.cancelled(job_seq):
                stopped = "cancelled"
                break

            audio = getattr(chunk, "audio", chunk)
            samples = np.asarray(mx.array(audio).astype(mx.float32))
            samples = np.clip(samples.reshape(-1), -1.0, 1.0)
            seconds = len(samples) / SAMPLE_RATE

            # Runaway guard. Checked before the chunk is handed over, so
            # nothing past the ceiling is ever audible.
            if produced + seconds > limit:
                stopped = "truncated"
                break
            if time.monotonic() > deadline:
                stopped = "timeout"
                break

            seq += 1
            path = os.path.join(workdir, f"chunk_{seq:06d}.wav")
            with wave.open(path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(SAMPLE_RATE)
                handle.writeframes((samples * 32767).astype("<i2").tobytes())

            produced += seconds
            emit({"event": "audio", "id": request_id,
                  "path": path, "seconds": round(seconds, 3)})

        if stopped in ("truncated", "timeout"):
            emit({"event": stopped, "id": request_id,
                  "seconds": round(produced, 2), "limit": round(limit, 2)})
        elif stopped == "cancelled":
            emit({"event": "cancelled", "id": request_id,
                  "seconds": round(produced, 2)})
        else:
            emit({"event": "done", "id": request_id,
                  "seconds": round(produced, 2)})
    except Exception as exc:
        emit({"event": "error", "id": request_id, "error": str(exc)[:300]})
    return seq


def main() -> None:
    try:
        from mlx_audio.tts.utils import load_model
        import mlx.core as mx
        import numpy as np
    except Exception as exc:
        emit({"event": "fatal", "error": f"imports failed: {exc}"})
        return

    try:
        model = load_model(MODEL)
    except Exception as exc:
        emit({"event": "fatal", "error": f"model load failed: {exc}"})
        return

    workdir = tempfile.mkdtemp(prefix="mike-qwen-tts-")
    emit({"event": "ready", "model": MODEL, "voice": VOICE,
          "instruct": INSTRUCT, "workdir": workdir})

    work: queue.Queue = queue.Queue()
    ctrl = Ctrl()
    reader = threading.Thread(target=_reader, args=(work, ctrl), daemon=True)
    reader.start()

    seq = 0
    while not ctrl.quit:
        try:
            msg = work.get(timeout=0.2)
        except queue.Empty:
            continue
        if msg is None:                          # quit sentinel
            break

        request_id = msg.get("id", 0)
        job_seq = msg.get("_seq", 0)
        text = (msg.get("text") or "").strip()
        if not text:
            emit({"event": "done", "id": request_id, "seconds": 0.0})
            continue

        # A cancel that landed while this job sat in the queue means it was
        # part of an abandoned reply — drop it without generating. The
        # comparison is by job number, so a genuinely newer utterance (higher
        # seq than any prior cancel) is never mistaken for a stale one.
        if ctrl.cancelled(job_seq):
            emit({"event": "cancelled", "id": request_id, "seconds": 0.0})
            continue

        seq = _generate(
            model, mx, np, workdir, request_id, text, seq, job_seq, ctrl)


if __name__ == "__main__":
    try:
        main()
    finally:
        # Chunks are written here and deleted as they play; anything left is
        # from an utterance that was interrupted.
        import shutil as _shutil
        for _dir in [d for d in (globals().get("workdir"),) if d]:
            _shutil.rmtree(_dir, ignore_errors=True)
