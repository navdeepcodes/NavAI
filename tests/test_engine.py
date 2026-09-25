"""Mike's own model engine: where it runs, what it sends, and what it finds."""
import json
from pathlib import Path

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
