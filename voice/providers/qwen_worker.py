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
         {"cmd": "ping"}
    out: {"event": "ready"}                      once, after the model loads
         {"event": "audio", "id": 7, "path": "/tmp/....wav", "seconds": 1.9}
         {"event": "done", "id": 7, "seconds": 6.4}
         {"event": "error", "id": 7, "error": "..."}
         {"event": "truncated", "id": 7, "seconds": 21.0, "limit": 20.4}

Chunks are written as files and their paths reported, rather than piped as
bytes: the parent plays them with afplay, which keeps audio handling in the
parent where interruption already works.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import wave

MODEL = os.environ.get("MIKE_QWEN_TTS_MODEL",
                       "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit")
VOICE = os.environ.get("MIKE_QWEN_TTS_VOICE", "Chelsie")
CHUNK_SECONDS = float(os.environ.get("MIKE_QWEN_TTS_CHUNK", "0.5"))
SAMPLE_RATE = 24000


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
    slowest_observed = 10.0 / 118.0        # seconds per character, measured
    # 1.8x the slowest run actually seen. Enough headroom that a normal but
    # unusually slow reading is never clipped; tight enough that a run at
    # twice the worst normal length is already stopped, rather than waiting
    # for the 96-second case to prove itself.
    return max(4.0, len(text) * slowest_observed * 1.8)


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
    emit({"event": "ready", "model": MODEL, "voice": VOICE, "workdir": workdir})

    seq = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        cmd = msg.get("cmd")
        if cmd == "quit":
            break
        if cmd == "ping":
            emit({"event": "pong"})
            continue
        if cmd != "speak":
            continue

        request_id = msg.get("id", 0)
        text = (msg.get("text") or "").strip()
        if not text:
            emit({"event": "done", "id": request_id, "seconds": 0.0})
            continue

        limit = duration_limit(text)
        deadline = time.monotonic() + max(20.0, limit * 3)
        produced = 0.0
        stopped = None

        try:
            for chunk in model.generate(
                text=text, voice=VOICE, verbose=False,
                stream=True, streaming_interval=CHUNK_SECONDS,
            ):
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

            if stopped:
                emit({"event": stopped, "id": request_id,
                      "seconds": round(produced, 2), "limit": round(limit, 2)})
            else:
                emit({"event": "done", "id": request_id,
                      "seconds": round(produced, 2)})
        except Exception as exc:
            emit({"event": "error", "id": request_id, "error": str(exc)[:300]})


if __name__ == "__main__":
    main()
