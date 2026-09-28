"""Mike's own model engine: where it runs, what it sends, and what it finds."""
import json
import threading
import time
from pathlib import Path

import pytest

from brain import engine as eng
from brain.providers.engine_provider import CONTEXT_OPEN, fold_system_messages


def _dev(name, desc, free, kind="vulkan"):
    return eng.Device(name, desc, free + 1000, free, Path("x.dll"), kind)


def test_a_discrete_gpu_beats_an_integrated_one_with_more_free_memory():
    igpu = _dev("Vulkan0", "Intel(R) Graphics", 8300)
    card = _dev("Vulkan1", "NVIDIA GeForce RTX 3050 Laptop GPU", 3800)
    assert eng.choose_device([igpu, card]) is card


def test_cuda_beats_vulkan_for_the_same_card():
    vk = _dev("Vulkan1", "NVIDIA GeForce RTX 4060", 7000)
    cu = _dev("CUDA0", "NVIDIA GeForce RTX 4060", 7000, kind="cuda")
    assert eng.choose_device([vk, cu]) is cu


def test_an_integrated_gpu_is_used_rather_than_the_cpu():
    igpu = _dev("Vulkan0", "Intel(R) Graphics", 8300)
    assert eng.choose_device([igpu]) is igpu and igpu.integrated


def test_no_gpu_with_room_means_the_cpu():
    assert eng.choose_device([_dev("Vulkan0", "Intel(R) UHD Graphics", 900)]) is None
    assert eng.choose_device([]) is None


def test_the_device_list_is_read_from_the_servers_own_words():
    m = eng._DEVICE_LINE.match("  Vulkan0: Intel(R) Graphics (9016 MiB, 8310 MiB free)")
    assert m.groups() == ("Vulkan0", "Intel(R) Graphics", "9016", "8310")


def test_later_system_messages_join_the_next_user_message():
    folded = fold_system_messages([
        {"role": "system", "content": "Mike"},
        {"role": "system", "content": "It's Friday."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
        {"role": "system", "content": "Notepad is focused."},
        {"role": "user", "content": "type hello"},
    ])
    assert [m["role"] for m in folded] == ["system", "user", "assistant", "user"]
    assert folded[1]["content"].startswith(CONTEXT_OPEN) and folded[1]["content"].endswith("hi")
    assert "Notepad is focused." in folded[3]["content"]


def test_folding_is_the_same_every_time_so_the_cache_holds():
    msgs = [{"role": "system", "content": "Mike"}, {"role": "system", "content": "ctx"},
            {"role": "user", "content": "hi"}]
    assert fold_system_messages(msgs) == fold_system_messages(msgs)


def test_the_model_file_is_found_through_ollamas_manifest(tmp_path, monkeypatch):
    blob = tmp_path / "blobs" / "sha256-abc"
    blob.parent.mkdir()
    blob.write_bytes(b"gguf")
    manifest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.license", "digest": "sha256:lic"},
        {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}]}))
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    assert eng.model_blob("qwen3.5:9b") == (blob, "sha256:abc")


def test_mike_can_be_told_to_use_ollama_instead(monkeypatch):
    monkeypatch.setenv("MIKE_BRAIN", "ollama")
    assert eng.available() is False


def test_the_fixed_prompt_does_not_change_with_the_date():
    from brain.core_runtime import SYSTEM_PROMPT
    assert "{date}" not in SYSTEM_PROMPT and "Today's date" not in SYSTEM_PROMPT


def test_the_same_model_named_explicitly_stays_on_the_engine(monkeypatch):
    """The summariser names the chat model; sent to Ollama, it loaded a second
    9GB copy beside the engine's."""
    from brain import providers
    monkeypatch.setattr(eng, "available", lambda: True)
    providers._CACHE.clear()
    try:
        chat = providers.get_provider(model="qwen3.5:9b")
        assert type(getattr(chat, "local", chat)).__name__ == "EngineProvider"
        assert type(providers.get_provider(model="qwen2.5vl:3b")).__name__ == "OllamaProvider"
    finally:
        providers._CACHE.clear()


# ── quitting, and a server that can't load ────────────────────────────────

class _Proc:
    """A model server that loads nothing."""

    def __init__(self, returncode=None):
        self.returncode, self.killed = returncode, False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, 1

    def wait(self, timeout=None):
        return self.returncode


def _startable(tmp_path, monkeypatch):
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"exe")
    procs = []
    monkeypatch.setattr(eng.subprocess, "Popen", lambda *a, **k: procs.append(_Proc()) or procs[-1])
    monkeypatch.setattr(eng, "model_blob", lambda model: (tmp_path / "blob", "sha256:abc"))
    monkeypatch.setattr(eng, "_kill_with_parent", lambda proc: None)

    def refused(*a, **k):
        raise eng.requests.ConnectionError("nothing listening")

    monkeypatch.setattr(eng.requests, "get", refused)
    e = eng.LocalEngine("qwen3.5:9b", 16384, tmp_path / "state")
    monkeypatch.setattr(e, "_server", lambda: (exe, {}))
    monkeypatch.setattr(eng, "_ENGINE", e)
    return e, procs


def test_nothing_is_started_once_mike_is_closing(tmp_path, monkeypatch):
    e, procs = _startable(tmp_path, monkeypatch)
    eng.shutdown()
    try:
        with pytest.raises(eng.EngineClosing):
            e.start()
        assert procs == []
    finally:
        eng._closing.clear()


def test_quitting_waits_for_a_launch_under_way_and_stops_it(tmp_path, monkeypatch):
    """Measured: "Quitting" logged, then the warm-up launched a server, and
    the process ended before tying it to Mike's -- 9GB left running with no
    Mike, three times in a day."""
    e, procs = _startable(tmp_path, monkeypatch)
    launching = threading.Event()

    def slow_tie(proc):
        launching.set()
        time.sleep(0.3)

    monkeypatch.setattr(eng, "_kill_with_parent", slow_tie)
    outcome = []

    def warm_up():
        try:
            e.start(background=True)
        except Exception as exc:
            outcome.append(exc)

    t = threading.Thread(target=warm_up)
    t.start()
    assert launching.wait(5)
    try:
        eng.shutdown()                       # quit, with the launch half done
        t.join(10)
        assert procs and procs[0].killed, "the server it launched is stopped"
        assert outcome and isinstance(outcome[0], eng.EngineClosing)
    finally:
        eng._closing.clear()


def test_a_server_that_ran_out_of_memory_says_so(tmp_path, monkeypatch):
    """Only "exited (code 1)" reached the log and the chat, while the server's
    own log said it couldn't allocate its buffers."""
    e, _ = _startable(tmp_path, monkeypatch)

    def popen(*args, stdout=None, **kwargs):
        stdout.write("ggml_gallocr_reserve_n_impl: failed to allocate Vulkan0 buffer of size "
                     "175505408\nllama_init_from_model: failed to initialize the context\n")
        stdout.flush()
        return _Proc(returncode=1)

    monkeypatch.setattr(eng.subprocess, "Popen", popen)
    with pytest.raises(eng.EngineUnavailable, match="not enough free memory"):
        e.start()


class _Engine:
    model, num_ctx, device = "qwen3.5:9b", 16384, None

    def __init__(self, error):
        self.error = error

    def start(self, background=False):
        raise self.error


def test_when_the_engine_cant_start_plain_ollama_answers(monkeypatch):
    """Not Ollama inside a second Fast mode: that one called Cloudflare again
    17s after the first had stepped back from it."""
    from brain import providers
    from brain.providers.engine_provider import EngineProvider
    providers._CACHE.clear()
    try:
        p = EngineProvider(_Engine(eng.EngineUnavailable("the model server exited (code 1)")))
        assert p._ready() is False
        assert type(p._fallback).__name__ == "OllamaProvider"
    finally:
        providers._CACHE.clear()


def test_while_quitting_the_engine_does_not_hand_over_to_ollama():
    """Ollama would load its own 9GB copy -- and keep it after Mike is gone."""
    from brain.providers.engine_provider import EngineProvider
    p = EngineProvider(_Engine(eng.EngineClosing("Mike is closing")))
    with pytest.raises(eng.EngineClosing):
        p._ready()
    assert p._fallback is None


# ── a prompt read that stops moving ──────────────────────────────────────

def _reading(tmp_path, monkeypatch, progress, finish_after=None):
    """A server reading the prompt: `progress` yields tokens-read per check;
    the read itself finishes after `finish_after` seconds (never, if None)."""
    e = eng.LocalEngine("qwen3.5:9b", 16384, tmp_path)
    e.port = 1
    released = threading.Event()

    def post(*a, **k):
        released.wait(finish_after if finish_after is not None else 30)
        class R:
            def raise_for_status(self):
                if not released.is_set() and finish_after is None:
                    raise eng.requests.ConnectionError("server gone")
        return R()

    monkeypatch.setattr(eng.requests, "post", post)
    monkeypatch.setattr(e, "_tokens_read", lambda: next(progress, None))
    stopped = []
    monkeypatch.setattr(e, "stop", lambda: (stopped.append(1), released.set()))
    monkeypatch.setattr(eng, "WATCH_EVERY", 0.02)
    return e, stopped


def test_a_read_that_stops_moving_is_stopped(tmp_path, monkeypatch):
    """Measured: 2,048 tokens in 25s, then nothing for twenty minutes -- hung
    on the graphics chip that also draws the screen."""
    monkeypatch.setattr(eng, "STALL_TIMEOUT", 0.3)
    e, stopped = _reading(tmp_path, monkeypatch, iter([0, 2048] + [2048] * 1000))
    with pytest.raises(eng.EngineUnavailable, match="progress"):
        e._read_prompt("prompt")
    assert stopped == [1]


def test_a_slow_read_that_keeps_moving_is_left_to_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "STALL_TIMEOUT", 0.3)
    e, stopped = _reading(tmp_path, monkeypatch, iter(range(0, 100000, 10)), finish_after=1.0)
    e._read_prompt("prompt")
    assert stopped == []
