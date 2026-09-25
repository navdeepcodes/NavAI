"""Mike's own model server: the same model, run so a restart costs seconds.

Ollama runs the model through llama-server, but it cannot save what the model
has already read. Mike's fixed prompt -- instructions plus every tool's schema
-- is ~8,300 tokens, and after every Ollama start the model read all of it
again before the first reply. Measured on the target laptop (Core Ultra 5
125U, iGPU): 146s at 56 tok/s. On a machine without a usable GPU the same read
runs at ~15 tok/s: nine minutes.

This runs the llama-server and model file Ollama already installed, with two
differences that matter:
  - the model's state after reading the fixed prompt is saved to disk once and
    restored at every later start (0.2s for 8,281 tokens, measured);
  - one slot and the model's own chat template, so requests land where the
    cache is.
Measured after a restart: first answer in 2.8-4.1s instead of ~150s.

The saved state belongs to one exact prompt, model and server, and is keyed by
a hash of all three; when any of them changes it is rebuilt once. Nothing here
is required: if the server or the model can't be found or won't start, Mike
uses Ollama exactly as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from logs.logger import logger

START_TIMEOUT = 120
PREFIX_FILE = "prefix-{key}.bin"


class EngineUnavailable(RuntimeError):
    pass


def _ollama_lib() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "lib" / "ollama"


def _ollama_models() -> Path:
    return Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")


def model_blob(model: str) -> tuple[Path, str]:
    """The GGUF file Ollama keeps for `model` ("qwen3.5:9b"), and its digest."""
    name, _, tag = model.partition(":")
    manifest = _ollama_models() / "manifests" / "registry.ollama.ai" / "library" / name / (tag or "latest")
    try:
        layers = json.loads(manifest.read_text(encoding="utf-8")).get("layers", [])
    except (OSError, ValueError) as exc:
        raise EngineUnavailable(f"no Ollama manifest for {model}: {exc}") from exc
    for layer in layers:
        if layer.get("mediaType") == "application/vnd.ollama.image.model":
            digest = str(layer.get("digest", ""))
            blob = _ollama_models() / "blobs" / digest.replace(":", "-")
            if blob.exists():
                return blob, digest
    raise EngineUnavailable(f"the model file for {model} is not on disk")


_DEVICE_LINE = re.compile(r"^\s*(\w+?\d+):\s+(.+?)\s+\((\d+) MiB,\s+(\d+) MiB free\)")
# GPUs that share system RAM. A discrete card is faster at the same free memory.
_INTEGRATED = re.compile(r"Intel\(R\) (?:UHD |Iris |HD )?(?:Xe )?Graphics|Intel\(R\) Arc\(TM\) Graphics"
                         r"|Radeon\(TM\)(?: \d{3,4}M)? Graphics|Radeon\(TM\) \d{3,4}M", re.I)
# Backend kinds, best first when devices are otherwise equal.
_KIND_RANK = {"cuda": 3, "hip": 2, "vulkan": 1}
MIN_GPU_FREE_MIB = 1500


@dataclass
class Device:
    name: str               # "Vulkan0", "CUDA0"
    description: str        # "Intel(R) Graphics"
    total_mib: int
    free_mib: int
    backend: Path           # the ggml backend library that drives it
    kind: str               # cuda / hip / vulkan

    @property
    def integrated(self) -> bool:
        return self.kind == "vulkan" and bool(_INTEGRATED.search(self.description))

    def rank(self) -> tuple:
        return (not self.integrated, _KIND_RANK.get(self.kind, 0), self.free_mib)

    def describe(self) -> str:
        where = "integrated GPU" if self.integrated else "GPU"
        return f"{self.description} ({where}, {self.kind}, {self.free_mib} MiB free)"


def _gpu_backends(lib: Path) -> list[tuple[str, Path]]:
    found = []
    for sub in sorted(lib.iterdir(), reverse=True) if lib.exists() else []:
        for kind, dll in (("cuda", "ggml-cuda.dll"), ("hip", "ggml-hip.dll"), ("vulkan", "ggml-vulkan.dll")):
            if (sub / dll).exists():
                found.append((kind, sub / dll))
    return found


def probe_devices(exe: Path, lib: Path) -> list[Device]:
    """Every GPU the installed backends can drive, with its free memory now.
    The backends are asked in parallel: one that can't load (no NVIDIA card,
    say) fails fast and costs nothing."""
    devices: list[Device] = []
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    def ask(kind: str, dll: Path) -> None:
        try:
            out = subprocess.run([str(exe), "--list-devices"], env=dict(os.environ, GGML_BACKEND_PATH=str(dll)),
                                 capture_output=True, text=True, timeout=30, creationflags=flags).stdout
        except Exception:
            return
        for line in out.splitlines():
            m = _DEVICE_LINE.match(line)
            if m:
                devices.append(Device(m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), dll, kind))

    threads = [threading.Thread(target=ask, args=b, daemon=True) for b in _gpu_backends(lib)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=35)
    return devices


def choose_device(devices: list[Device]) -> Device | None:
    """The best place to run: a discrete GPU over one that shares system RAM,
    then the faster backend, then the most free memory. None -- the CPU --
    only when no GPU has room for a meaningful part of the model."""
    usable = [d for d in devices if d.free_mib >= MIN_GPU_FREE_MIB]
    return max(usable, key=Device.rank) if usable else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kill_with_parent(proc: subprocess.Popen) -> None:
    """Tie the server's life to Mike's: if Mike exits or is killed, Windows
    ends the server too, so a crash can't leave 5GB of model resident."""
    if sys.platform != "win32":
        return
    try:
        import win32api
        import win32con
        import win32job

        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, proc.pid)
        win32job.AssignProcessToJobObject(job, handle)
        proc._mike_job = job            # the job lives as long as the process object
    except Exception:
        logger.debug("Could not tie the model server to Mike's process.", exc_info=True)


class LocalEngine:
    """One llama-server for this Mike process."""

    def __init__(self, model: str, num_ctx: int, state_dir: Path) -> None:
        self.model = model
        self.num_ctx = num_ctx
        self.state_dir = state_dir
        self.port = 0
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._prefix_ready = threading.Event()
        self.device: Device | None = None

    # ── finding the pieces ───────────────────────────────────
    def _server(self) -> tuple[Path, dict]:
        """The server, and where it should run: the best GPU on this machine,
        found by asking every installed backend what it can see. Run bare,
        the server loads no GPU backend and reads prompts at CPU speed (15 vs
        56 tok/s measured on this laptop's iGPU)."""
        lib = _ollama_lib()
        exe = lib / "llama-server.exe"
        if not exe.exists():
            raise EngineUnavailable(f"no llama-server at {exe}")
        env = dict(os.environ)
        devices = probe_devices(exe, lib)
        self.device = choose_device(devices)
        if self.device is not None:
            env["GGML_BACKEND_PATH"] = str(self.device.backend)
            logger.info("Running the model on %s; seen: %s.", self.device.describe(),
                        "; ".join(d.describe() for d in devices))
        else:
            logger.info("No GPU with room for the model (%s); running on the CPU.",
                        "; ".join(d.describe() for d in devices) or "none found")
        return exe, env

    def _args(self, exe: Path, blob: Path) -> list[str]:
        # --mmproj on the same file, as Ollama runs it: this model's vision
        # lives in the one blob, and it is what lets Mike read a screenshot.
        args = [str(exe), "--model", str(blob), "--mmproj", str(blob),
                "--host", "127.0.0.1", "--port", str(self.port),
                "--jinja", "-c", str(self.num_ctx), "-np", "1",
                "--flash-attn", "auto", "--slot-save-path", str(self.state_dir),
                "--no-webui", "--offline"]
        if self.device is not None:
            # No -ngl: --fit (on by default) puts as many layers on the GPU as
            # its free memory allows and the rest on the CPU, instead of
            # failing to load or spilling blindly.
            args += ["--device", self.device.name]
        else:
            args += ["-ngl", "0"]
        return args

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ── lifecycle ────────────────────────────────────────────
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.running():
                return
            exe, env = self._server()
            blob, digest = model_blob(self.model)
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.port = _free_port()
            self._identity = f"{digest}|{exe.stat().st_size}|{exe.stat().st_mtime_ns}|{self.num_ctx}"
            log = open(self.state_dir / "server.log", "w", encoding="utf-8", errors="replace")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(self._args(exe, blob), env=env, stdout=log,
                                          stderr=subprocess.STDOUT, creationflags=flags)
            _kill_with_parent(self._proc)
            t0 = time.monotonic()
            while time.monotonic() - t0 < START_TIMEOUT:
                if self._proc.poll() is not None:
                    raise EngineUnavailable(f"the model server exited (code {self._proc.returncode})")
                try:
                    if requests.get(self.base_url + "/health", timeout=2).status_code == 200:
                        logger.info("Model server up in %.1fs on port %d.", time.monotonic() - t0, self.port)
                        self._release_ollama_copy()
                        return
                except requests.RequestException:
                    pass
                time.sleep(0.3)
            self.stop()
            raise EngineUnavailable("the model server did not start in time")

    def _release_ollama_copy(self) -> None:
        """If Ollama still holds this model from before, let it go: two
        copies of a 6GB model don't fit on a 16GB laptop."""
        try:
            from config import ollama as cfg

            requests.post(cfg.OLLAMA_HOST + "/api/generate",
                          json={"model": self.model, "keep_alive": 0}, timeout=5)
        except Exception:
            pass

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass

    # ── the fixed prompt, read once ──────────────────────────
    def prefix_text(self, system: str, tools: list[dict]) -> str:
        """Exactly how the model sees Mike's fixed prompt: the system turn with
        the tools, as the model's own template renders it, up to where the
        next message begins."""
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": "x"}],
                "tools": tools or None, "chat_template_kwargs": {"enable_thinking": False}}
        r = requests.post(self.base_url + "/apply-template", json=body, timeout=60)
        r.raise_for_status()
        prompt = r.json()["prompt"]
        cut = prompt.rfind("<|im_start|>user")
        if cut <= 0:
            raise EngineUnavailable("could not find where the fixed prompt ends")
        return prompt[:cut]

    def ensure_prefix(self, system: str, tools: list[dict]) -> str:
        """Have the model's state for the fixed prompt in place: restored from
        disk when it was saved before, otherwise read now and saved. Returns
        "restored", "built" or "unchanged"."""
        prefix = self.prefix_text(system, tools)
        key = hashlib.sha256((self._identity + "\0" + prefix).encode()).hexdigest()[:16]
        name = PREFIX_FILE.format(key=key)
        if getattr(self, "_prefix_key", None) == key:
            return "unchanged"
        t0 = time.monotonic()
        if (self.state_dir / name).exists():
            r = requests.post(self.base_url + "/slots/0?action=restore", json={"filename": name}, timeout=120)
            if r.ok:
                self._prefix_key = key
                self._prefix_ready.set()
                logger.info("Restored the model's reading of Mike's prompt in %.1fs (%s tokens).",
                            time.monotonic() - t0, r.json().get("n_restored"))
                return "restored"
            logger.warning("Could not restore the saved prompt state (%s); reading it again.", r.status_code)
        r = requests.post(self.base_url + "/completion",
                          json={"prompt": prefix, "n_predict": 0, "cache_prompt": True}, timeout=3600)
        r.raise_for_status()
        requests.post(self.base_url + "/slots/0?action=save", json={"filename": name},
                      timeout=300).raise_for_status()
        for old in self.state_dir.glob(PREFIX_FILE.format(key="*")):
            if old.name != name:
                try:
                    old.unlink()
                except OSError:
                    pass
        self._prefix_key = key
        self._prefix_ready.set()
        logger.info("Read Mike's prompt once (%.0fs) and saved it; later starts restore it.",
                    time.monotonic() - t0)
        return "built"


_ENGINE: LocalEngine | None = None


def available() -> bool:
    """Whether Mike can run its own engine here: Windows, with the server and
    the model file Ollama installed. Cheap -- nothing is started."""
    if sys.platform != "win32" or os.environ.get("MIKE_BRAIN") == "ollama":
        return False
    try:
        from config import ollama as cfg

        model_blob(cfg.OLLAMA_CHAT_MODEL)
        return (_ollama_lib() / "llama-server.exe").exists()
    except Exception:
        return False


def engine() -> LocalEngine:
    global _ENGINE
    if _ENGINE is None:
        from config import ollama as cfg
        from hostplatform import storage

        _ENGINE = LocalEngine(cfg.OLLAMA_CHAT_MODEL, cfg.NUM_CTX, storage.data_dir() / "engine")
    return _ENGINE


def shutdown() -> None:
    if _ENGINE is not None:
        _ENGINE.stop()
