"""Piper as Mike's Windows neural voice — chosen by measurement.

Benchmarked head-to-head against Kokoro-82M (int8 ONNX) on the target hardware
(Intel Core Ultra 5, no GPU): Kokoro is the more natural engine but runs at
~0.5x real time there, so a sentence takes ~7 s to first audio and playback
underruns constantly. Piper runs 6-7x real time on the same CPU, first audio
in ~0.3 s, zero streaming gaps, ~200 MB RAM. For a student laptop the win is
decisive, and a laggy natural voice feels *worse* than a fast clear one, so
Piper is the Windows default. Kokoro stays reachable behind this same
interface for machines that can run it; SAPI remains the unbreakable fallback.

The architecture is a streaming pipeline, not synthesize-then-speak:

    LLM streams -> a sentence is ready -> it's handed to piper -> piper emits
    raw PCM as it generates -> the *next* sentence synthesizes while the
    current one plays -> playback is continuous -> a barge-in stops it at once.

One persistent piper.exe (the model loads once), a reader thread draining its
raw-PCM stdout, a synth thread that paces one sentence into the engine at a
time, and a playback thread that plays finished sentences in order through
sounddevice — the same playback path the other voices already use.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from logs.logger import logger
from voice.providers.base import VoiceProvider

# Speak 1.15x faster than the model's natural pace — a touch quicker reads as
# present and conversational rather than a measured narration. Piper's
# --length_scale is inverse to speed (lower = faster), so 1/1.15.
SPEED = 1.15
LENGTH_SCALE = round(1.0 / SPEED, 3)

# A little trailing silence per sentence keeps ends from clipping without
# adding the default 0.2 s of latency between streamed sentences.
SENTENCE_SILENCE = 0.08

DEFAULT_VOICE = "en_US-amy-medium"

# The voices bundled with Mike, and how they read. English-native, all
# benchmarked with zero streaming gaps on the target hardware.
VOICES = {
    "en_US-amy-medium":    "Amy — warm, natural female (US)",
    "en_US-lessac-medium": "Lessac — clear, neutral (US)",
    "en_US-ryan-high":     "Ryan — rich, expressive male (US)",
}


def _piper_home() -> Path | None:
    """The directory holding piper.exe and its voices, wherever Mike is run
    from: bundled next to the frozen app, or the repo's runtime tree in dev."""
    candidates = []
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        candidates.append(Path(mei) / "piper")
        candidates.append(Path(os.path.dirname(sys.executable)) / "piper")
    env = os.environ.get("MIKE_PIPER_HOME")
    if env:
        candidates.append(Path(env))
    # repo/runtime/piper — voice/providers/piper.py -> repo root is parents[2]
    candidates.append(Path(__file__).resolve().parents[2] / "runtime" / "piper")
    for c in candidates:
        if (c / "piper.exe").exists() or (c / "piper").exists():
            return c
    return None


class PiperVoice(VoiceProvider):

    name = "piper"
    queues = True

    def __init__(self, voice: str | None = None,
                 length_scale: float | None = None) -> None:
        self._home = _piper_home()
        self._voice = voice or self._preference("voice_piper_voice", DEFAULT_VOICE)
        if self._voice not in VOICES and self._home is not None:
            # a hand-set voice we don't know: only trust it if the model is there
            model = self._home / "voices" / f"{self._voice}.onnx"
            if not model.exists():
                self._voice = DEFAULT_VOICE
        self._length_scale = length_scale if length_scale is not None else LENGTH_SCALE
        self._sr = 22050

        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._raw_q: queue.Queue = queue.Queue()
        self._submit_q: queue.Queue = queue.Queue()
        self._play_q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        # Bumped by every stop(). Text and audio carry the generation they were
        # queued in, and anything from an older generation is dropped — so an
        # interrupted reply can never resume, even if a new one is queued in
        # the same instant the old audio was being written.
        self._gen = 0
        self._closing = False
        self._playing = threading.Event()
        self._synthing = threading.Event()
        self._reader: threading.Thread | None = None
        self._synth: threading.Thread | None = None
        self._player: threading.Thread | None = None

        self._healthy = True
        self._last_failure = ""
        self._last_truncation = ""
        self._first_audio_ms = 0

    @staticmethod
    def _preference(key: str, default: str) -> str:
        try:
            from config import preferences
            return str(preferences.get(key, default) or default)
        except Exception:
            return default

    def _model(self) -> Path | None:
        if self._home is None:
            return None
        return self._home / "voices" / f"{self._voice}.onnx"

    # ── availability ──────────────────────────────────────
    def available(self) -> tuple[bool, str]:
        if self._home is None:
            return False, "the Piper runtime is not bundled with this build"
        exe = self._home / "piper.exe"
        if not exe.exists():
            return False, f"piper.exe is missing from {self._home}"
        model = self._model()
        if model is None or not model.exists():
            return False, f"the voice model {self._voice} is not installed"
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
        except Exception as exc:
            return False, f"audio playback is unavailable: {exc}"
        return True, f"Piper — {VOICES.get(self._voice, self._voice)}"

    # ── the worker ────────────────────────────────────────
    def warm_up(self) -> None:
        self._ensure_worker()

    def _ensure_worker(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            model = self._model()
            if self._home is None or model is None or not model.exists():
                self._last_failure = "piper runtime or voice model missing"
                return False
            # read the true sample rate from the voice config
            try:
                import json
                with open(str(model) + ".json", "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
                self._sr = int(cfg.get("audio", {}).get("sample_rate", 22050))
            except Exception:
                self._sr = 22050

            exe = self._home / "piper.exe"
            try:
                self._proc = subprocess.Popen(
                    [str(exe), "-m", str(model), "--output_raw",
                     "--length_scale", str(self._length_scale),
                     "--sentence_silence", str(SENTENCE_SILENCE)],
                    cwd=str(self._home),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                self._last_failure = f"piper would not start: {exc}"
                logger.warning("Piper %s", self._last_failure)
                return False

            self._closing = False
            self._stop.clear()
            self._raw_q = queue.Queue()
            self._reader = threading.Thread(target=self._read_pipe, daemon=True)
            self._synth = threading.Thread(target=self._synth_loop, daemon=True)
            self._player = threading.Thread(target=self._play_loop, daemon=True)
            self._reader.start()
            self._synth.start()
            self._player.start()
            logger.info("Piper ready (%s, %.2fx)", self._voice, SPEED)
            return True

    def _read_pipe(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        while True:
            try:
                chunk = proc.stdout.read(4096)
            except Exception:
                self._raw_q.put(None)
                return
            if not chunk:
                self._raw_q.put(None)
                return
            self._raw_q.put((time.perf_counter(), chunk))

    def _flush_pipe(self) -> None:
        """Discard any PCM still arriving from a cancelled sentence, so the
        next one starts from a clean, quiet pipe."""
        # drain what's queued
        while True:
            try:
                self._raw_q.get_nowait()
            except queue.Empty:
                break
        # wait briefly for the pipe to go quiet (a barge-in leaves a tail)
        deadline = time.perf_counter() + 0.4
        while time.perf_counter() < deadline:
            try:
                self._raw_q.get(timeout=0.06)
            except queue.Empty:
                return

    def _synth_loop(self) -> None:
        while not self._closing:
            try:
                gen, text = self._submit_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if gen != self._gen or self._proc is None:
                continue
            self._synthing.set()
            try:
                self._flush_pipe()
                if gen != self._gen:
                    continue
                try:
                    assert self._proc.stdin is not None
                    line = text.replace("\n", " ") + "\n"
                    self._proc.stdin.write(line.encode("utf-8"))
                    self._proc.stdin.flush()
                except Exception as exc:
                    self._fail(text, f"could not reach piper: {exc}")
                    continue
                pcm = self._read_sentence(gen)
                if pcm is None or gen != self._gen:
                    continue
                if pcm.size:
                    self._play_q.put((gen, pcm))
                else:
                    self._fail(text, "piper produced no audio")
            finally:
                self._synthing.clear()

    def _read_sentence(self, gen: int):
        import numpy as np
        buf = bytearray()
        first = None
        last = None
        start = time.perf_counter()
        while True:
            if gen != self._gen:
                return None
            try:
                item = self._raw_q.get(timeout=0.03)
            except queue.Empty:
                if buf and last and (time.perf_counter() - last) > 0.15:
                    break
                if time.perf_counter() - start > 30:
                    self._last_truncation = "piper generation exceeded 30s"
                    break
                continue
            if item is None:                       # EOF: worker died
                self._proc = None
                break
            ts, chunk = item
            if first is None:
                first = ts
                self._first_audio_ms = round((ts - start) * 1000)
            buf.extend(chunk)
            last = ts
        return np.frombuffer(bytes(buf), dtype=np.int16)

    #: Audio is written in ~30ms blocks, so an interruption lands within one.
    _BLOCK_SECONDS = 0.03

    def _play_loop(self) -> None:
        """Play finished sentences through ONE output stream owned by this
        thread.

        Only this thread ever touches the audio device. The first version used
        sounddevice's global play()/stop() — one module-level stream, no lock —
        from this thread while stop() ran on the GUI thread (every barge-in)
        and the wake word held its own PortAudio stream on a third. Racing on
        that global can close a stream underneath PortAudio's callback thread:
        a native crash with no Python frame. Now stop() only bumps a
        generation counter, and this thread aborts its own stream when it sees
        it. Keeping one stream open also makes consecutive sentences seamless
        instead of reopening the device for each.
        """
        import sounddevice as sd

        stream = None
        try:
            while not self._closing:
                try:
                    gen, pcm = self._play_q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if gen != self._gen:
                    continue
                try:
                    if stream is None:
                        stream = sd.OutputStream(samplerate=self._sr, channels=1,
                                                 dtype="int16")
                        stream.start()
                    self._playing.set()
                    data = pcm.reshape(-1, 1)
                    block = max(256, int(self._sr * self._BLOCK_SECONDS))
                    for i in range(0, len(data), block):
                        if gen != self._gen or self._closing:
                            stream.abort()          # drop anything still queued
                            stream.start()
                            break
                        stream.write(data[i:i + block])
                except Exception as exc:
                    logger.warning("Piper playback failed: %s", exc)
                    self._healthy = False
                    try:
                        if stream is not None:
                            stream.close()
                    except Exception:
                        pass
                    stream = None
                finally:
                    self._playing.clear()
        finally:
            if stream is not None:
                try:
                    stream.abort()
                    stream.close()
                except Exception:
                    pass

    # ── speaking ──────────────────────────────────────────
    def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        self.stop()
        if not self._ensure_worker():
            return False
        self._stop.clear()
        return self._submit(text)

    def enqueue(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        if not self._ensure_worker():
            return False
        self._stop.clear()
        return self._submit(text)

    def _submit(self, text: str) -> bool:
        try:
            self._submit_q.put((self._gen, text))
            return True
        except Exception as exc:
            self._last_failure = f"could not queue text: {exc}"
            return False

    def _fail(self, text: str, reason: str) -> None:
        self._last_failure = reason
        self._healthy = False
        logger.warning("Piper could not speak (%s)", reason)
        handler = self.on_failure
        if handler and not self._stop.is_set():
            try:
                handler(text, reason)
            except Exception:
                logger.exception("Voice fallback failed.")

    def is_speaking(self) -> bool:
        if self._stop.is_set():
            return False
        return (self._playing.is_set() or self._synthing.is_set()
                or not self._submit_q.empty() or not self._play_q.empty())

    def stop(self) -> None:
        # Only mark the reply as abandoned. The playback thread owns the audio
        # stream and aborts it within one ~30ms block when it sees the new
        # generation — this may be called from the GUI thread, which must
        # never touch the device itself (see _play_loop).
        self._gen += 1
        self._stop.set()
        # drop everything queued — it's part of the reply just interrupted
        for q in (self._submit_q, self._play_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def shutdown(self) -> None:
        self._closing = True
        self.stop()
        # Wait for the playback thread to close its audio stream (and the synth
        # thread to let go of the pipe) before returning. Returning while a
        # stream is still open let PortAudio's own exit-time teardown race the
        # closing stream — heap corruption at exit.
        for thread in (self._player, self._synth):
            if thread is not None and thread.is_alive() \
                    and thread is not threading.current_thread():
                thread.join(timeout=1.5)
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._proc = None

    # ── reporting ─────────────────────────────────────────
    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def first_audio_ms(self) -> int:
        return self._first_audio_ms

    @property
    def last_failure(self) -> str:
        return self._last_failure

    @property
    def last_truncation(self) -> str:
        return self._last_truncation
