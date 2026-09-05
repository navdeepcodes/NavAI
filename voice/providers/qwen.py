"""Qwen3-TTS 0.6B (4-bit) as one of Mike's voices.

Three decisions shape this file, all of them made from measurement.

**It runs in a separate process.** Not for isolation theatre — for three
concrete reasons. The runtime it needs pins `transformers==5.0.0rc3`, and
Mike's own environment is certified against a passing test suite that should
not take on a release candidate. Killing a process is the fastest and most
complete way to stop speech, which is exactly what barge-in needs. And a
model that crashes takes its own process with it rather than Mike.

**The model is loaded once and kept.** Loading costs 1.2 s and 0.88 GB. A
process per utterance would pay that every sentence; a persistent worker pays
it once, at first use.

**Playback happens here, not in the worker.** The worker writes chunks and
reports paths; this side plays them with `afplay` — the same shape as the
native voice, so stopping is the same operation and the lifecycle code that
already works keeps working.

Everything about it is optional. If the worker will not start, or dies, or
falls silent, `available()` says so and the caller uses the native voice.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from logs.logger import logger
from voice.providers.base import VoiceProvider

# The interpreter with mlx-audio installed. Deliberately not Mike's own.
DEFAULT_PYTHON = Path.home() / ".mike-tts-bench" / "bin" / "python"
DEFAULT_HF_HOME = Path.home() / ".mike-tts-bench" / "hf"

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"

# The nine voices this model ships with, and what they actually sound like.
# Recorded here rather than left to be rediscovered: the English-native ones
# are the short list for Mike, and the rest are here so the choice is visible
# rather than hidden in a model card.
VOICES = {
    "Ryan":     "dynamic male, strong rhythmic drive (English)",
    "Aiden":    "sunny American male, clear midrange (English)",
    "Serena":   "warm, gentle young female (Chinese-native)",
    "Vivian":   "bright, slightly edgy young female (Chinese-native)",
    "Uncle_Fu": "seasoned male, low mellow timbre (Chinese-native)",
    "Dylan":    "youthful Beijing male, clear natural timbre (Chinese-native)",
    "Eric":     "lively Chengdu male, husky brightness (Chinese-native)",
    "Ono_Anna": "playful Japanese female, light nimble timbre (Japanese-native)",
    "Sohee":    "warm Korean female, rich emotion (Korean-native)",
}

# Measured: the model loads in ~1.2 s alone, slower with the brain resident.
STARTUP_TIMEOUT = 90.0

# If the worker produces nothing at all for this long after being asked to
# speak, treat it as failed and fall back rather than leaving a silence.
FIRST_CHUNK_TIMEOUT = 12.0


class QwenVoice(VoiceProvider):

    name = "qwen"

    def __init__(self, python: Path | None = None, model: str = MODEL,
                 voice: str | None = None, instruct: str | None = None,
                 chunk_seconds: float = 0.5) -> None:
        self._python = Path(python or os.environ.get("MIKE_QWEN_PYTHON", DEFAULT_PYTHON))
        self._model = model
        self._voice = voice or self._preference("voice_qwen_speaker", "Ryan")
        # How Mike should sound, in words. Configurable because the right
        # answer is a matter of taste rather than of engineering, and because
        # a person should be able to change it without editing code.
        self._instruct = (
            instruct if instruct is not None
            else self._preference("voice_qwen_instruct", "")
        )
        self._chunk_seconds = chunk_seconds

        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._events: queue.Queue = queue.Queue()
        self._workdir: str | None = None
        self._ready = False
        self._lock = threading.Lock()

        self._player: subprocess.Popen | None = None
        self._playback: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._request = 0
        self._last_failure = ""
        self._last_truncation = ""

    @staticmethod
    def _preference(key: str, default: str) -> str:
        try:
            from config import preferences

            return str(preferences.get(key, default) or default)
        except Exception:
            return default


    # ── availability ──────────────────────────────────────

    def available(self) -> tuple[bool, str]:
        if not self._python.exists():
            return False, f"no interpreter at {self._python}"
        if shutil.which("afplay") is None:
            return False, "afplay is not on this machine"
        weights = DEFAULT_HF_HOME / "hub" / f"models--{self._model.replace('/', '--')}"
        if not weights.exists():
            return False, f"model weights are not downloaded ({self._model})"
        if self._voice not in VOICES:
            return False, (f"unknown voice {self._voice!r}; this model has: "
                           + ", ".join(sorted(VOICES)))
        return True, f"Qwen3-TTS 4-bit ({self._voice})"

    # ── the worker ────────────────────────────────────────

    def warm_up(self) -> None:
        self._ensure_worker()

    def _ensure_worker(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None and self._ready:
                return True
            if self._proc is not None:
                self._kill_worker()

            env = dict(os.environ)
            env["HF_HOME"] = str(DEFAULT_HF_HOME)
            env["MIKE_QWEN_TTS_MODEL"] = self._model
            env["MIKE_QWEN_TTS_VOICE"] = self._voice
            env["MIKE_QWEN_TTS_INSTRUCT"] = self._instruct
            env["MIKE_QWEN_TTS_CHUNK"] = str(self._chunk_seconds)
            worker = Path(__file__).parent / "qwen_worker.py"

            try:
                self._proc = subprocess.Popen(
                    [str(self._python), str(worker)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env,
                )
            except Exception as exc:
                self._last_failure = f"worker would not start: {exc}"
                logger.warning("Qwen TTS %s", self._last_failure)
                return False

            self._events = queue.Queue()
            self._reader = threading.Thread(target=self._read_events, daemon=True)
            self._reader.start()

            started = time.monotonic()
            while time.monotonic() - started < STARTUP_TIMEOUT:
                try:
                    event = self._events.get(timeout=0.5)
                except queue.Empty:
                    if self._proc.poll() is not None:
                        self._last_failure = "worker exited during startup"
                        return False
                    continue
                if event.get("event") == "ready":
                    self._workdir = event.get("workdir")
                    self._ready = True
                    logger.info("Qwen TTS ready (%s, voice %s)", self._model, self._voice)
                    return True
                if event.get("event") == "fatal":
                    self._last_failure = str(event.get("error"))[:200]
                    logger.warning("Qwen TTS failed to start: %s", self._last_failure)
                    self._kill_worker()
                    return False

            self._last_failure = "worker did not become ready in time"
            self._kill_worker()
            return False

    def _read_events(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._events.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _kill_worker(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill()
            self._proc.wait(timeout=2)
        except Exception:
            pass
        self._proc = None
        self._ready = False
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    # ── speaking ──────────────────────────────────────────

    def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        self.stop()
        if not self._ensure_worker():
            return False

        self._request += 1
        request_id = self._request
        self._stop_flag.clear()
        self._last_truncation = ""

        try:
            assert self._proc is not None and self._proc.stdin is not None
            self._proc.stdin.write(
                json.dumps({"cmd": "speak", "text": text, "id": request_id}) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:
            self._last_failure = f"could not reach the worker: {exc}"
            logger.warning("Qwen TTS %s", self._last_failure)
            self._kill_worker()
            return False

        # Wait only for the first chunk. Returning here is what keeps the
        # agent loop free: everything after this plays on its own thread.
        first: dict | None = None
        deadline = time.monotonic() + FIRST_CHUNK_TIMEOUT
        while time.monotonic() < deadline:
            try:
                event = self._events.get(timeout=0.2)
            except queue.Empty:
                if self._proc is None or self._proc.poll() is not None:
                    self._last_failure = "worker died while generating"
                    return False
                continue
            kind = event.get("event")
            if kind == "audio":
                first = event
                break
            if kind in ("error", "fatal"):
                self._last_failure = str(event.get("error"))[:200]
                logger.warning("Qwen TTS error: %s", self._last_failure)
                return False
            if kind in ("done", "truncated", "timeout"):
                # Produced nothing audible at all.
                self._last_failure = f"worker returned {kind} with no audio"
                return False

        if first is None:
            self._last_failure = "no audio within the first-chunk timeout"
            logger.warning("Qwen TTS %s", self._last_failure)
            return False

        self._playback = threading.Thread(
            target=self._play_stream, args=(request_id, first), daemon=True)
        self._playback.start()
        return True

    def _play_stream(self, request_id: int, first: dict) -> None:
        """Play chunks as they arrive, stopping the moment stop() is called."""
        self._play_file(first.get("path"))
        while not self._stop_flag.is_set():
            try:
                event = self._events.get(timeout=0.3)
            except queue.Empty:
                if self._proc is None or self._proc.poll() is not None:
                    return
                continue
            kind = event.get("event")
            if event.get("id") != request_id:
                continue
            if kind == "audio":
                self._play_file(event.get("path"))
            elif kind in ("truncated", "timeout"):
                self._last_truncation = (
                    f"{kind} at {event.get('seconds')}s "
                    f"(ceiling {event.get('limit')}s)"
                )
                logger.warning("Qwen TTS %s — runaway generation stopped",
                               self._last_truncation)
                return
            elif kind in ("done", "error"):
                return

    def _play_file(self, path: str | None) -> None:
        if not path or self._stop_flag.is_set():
            return
        try:
            self._player = subprocess.Popen(
                ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while self._player.poll() is None:
                if self._stop_flag.is_set():
                    return
                time.sleep(0.01)
        except Exception as exc:
            logger.warning("Qwen TTS playback failed: %s", exc)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def is_speaking(self) -> bool:
        # Once stopping has been asked for, nothing is audible — even though
        # the playback thread takes a few milliseconds to notice and unwind.
        # Reporting "still speaking" there made stop() look like it had not
        # worked, and would have had the caller stopping twice.
        if self._stop_flag.is_set():
            return False
        if self._player is not None and self._player.poll() is None:
            return True
        return bool(self._playback is not None and self._playback.is_alive())

    def stop(self) -> None:
        self._stop_flag.set()
        player = self._player
        if player is not None:
            try:
                player.terminate()
                player.wait(timeout=1)
            except Exception:
                try:
                    player.kill()
                except Exception:
                    pass
        self._player = None
        # Drain anything the worker is still reporting for the abandoned
        # utterance, so the next one does not read stale events.
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self.stop()
        if self._proc is not None and self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        self._kill_worker()

    # ── reporting ─────────────────────────────────────────

    @property
    def last_failure(self) -> str:
        return self._last_failure

    @property
    def last_truncation(self) -> str:
        return self._last_truncation
