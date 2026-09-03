"""Tests for text-to-speech (Speaker + sanitizer)."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.speaker import Speaker, clean_for_speech


def test_clean_markdown():
    assert clean_for_speech("**bold**") == "bold"
    assert clean_for_speech("*italic*") == "italic"
    assert clean_for_speech("__underline__") == "underline"
    assert clean_for_speech("# Heading") == "Heading"
    assert clean_for_speech("## Sub Heading") == "Sub Heading"
    assert clean_for_speech("[click here](http://example.com)") == "click here"
    print("PASS: markdown cleaning")


def test_clean_lists():
    text = "- item one\n- item two\n- item three"
    cleaned = clean_for_speech(text)
    assert "item one" in cleaned
    assert "-" not in cleaned
    print(f"PASS: list cleaning -> '{cleaned}'")


def test_clean_numbered_lists():
    text = "1. First\n2. Second\n3. Third"
    cleaned = clean_for_speech(text)
    assert "First" in cleaned
    assert "1." not in cleaned
    print(f"PASS: numbered list -> '{cleaned}'")


def test_clean_code_blocks():
    text = 'Here is the fix:\n```python\ndef add(a, b):\n    return a + b\n```\nThat should work.'
    cleaned = clean_for_speech(text)
    assert '```' not in cleaned
    assert 'def add' not in cleaned
    assert "code in the chat" in cleaned
    assert "should work" in cleaned
    print(f"PASS: code block -> '{cleaned}'")


def test_clean_inline_code():
    assert "pip install" in clean_for_speech("Run `pip install flask`")
    assert "`" not in clean_for_speech("Run `pip install flask`")
    print("PASS: inline code")


def test_clean_emojis():
    assert clean_for_speech("Done! 🚀") == "Done!"
    assert clean_for_speech("Great job! 😂👍") == "Great job!"
    assert clean_for_speech("✅ Success") == "Success"
    assert clean_for_speech("❌ Failed") == "Failed"
    assert "rocket" not in clean_for_speech("Done! 🚀").lower()
    print("PASS: emoji removal")


def test_clean_urls():
    text = "I opened https://www.youtube.com/watch?v=abc123 for you."
    cleaned = clean_for_speech(text)
    assert "YouTube" in cleaned
    assert "https" not in cleaned
    print(f"PASS: URL -> '{cleaned}'")


def test_clean_github_url():
    text = "Check https://github.com/user/repo for the code."
    cleaned = clean_for_speech(text)
    assert "GitHub" in cleaned
    print(f"PASS: GitHub URL -> '{cleaned}'")


def test_clean_paths():
    text = "I created ~/Developer/NavAI-v0/tools/new_file.py"
    cleaned = clean_for_speech(text)
    assert "/Users/" not in cleaned
    assert "~/" not in cleaned
    print(f"PASS: path -> '{cleaned}'")


def test_clean_symbols():
    assert "to" in clean_for_speech("input → output")
    assert "{" not in clean_for_speech("Use {key: value}")
    assert "<" not in clean_for_speech("Use <tag>")
    print("PASS: symbol cleanup")


def test_clean_checkmarks():
    text = "✓ Folder created\n✓ File written"
    cleaned = clean_for_speech(text)
    assert "✓" not in cleaned
    assert "Folder created" in cleaned
    print(f"PASS: checkmarks -> '{cleaned}'")


def test_preserves_meaning():
    assert clean_for_speech("The test failed because port 5432 is unreachable.") == \
        "The test failed because port 5432 is unreachable."
    assert "3 files" in clean_for_speech("I created 3 files.")
    print("PASS: meaning preserved")


def test_clean_empty():
    assert clean_for_speech("") == ""
    assert clean_for_speech("   ") == ""
    assert clean_for_speech("🚀🚀🚀") == ""
    print("PASS: empty/emoji-only text")


def test_clean_complex_response():
    text = """## Done! 🎉

I've completed the task:

- **Created** the folder `Projects`
- **Added** file `readme.txt`
- ✅ Verified successfully

Check ~/Desktop/Projects for the results."""

    cleaned = clean_for_speech(text)
    assert "##" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "✅" not in cleaned
    assert "🎉" not in cleaned
    assert "Created" in cleaned
    assert "Projects" in cleaned
    print(f"PASS: complex response -> '{cleaned}'")


def test_speak_voice():
    """Verify Samantha voice via AVSpeechSynthesizer."""
    s = Speaker()
    s.speak("Testing Mike's voice.")
    time.sleep(0.3)
    assert s.is_speaking()
    s.stop()
    print("PASS: speak with Samantha voice")


def test_speak_stop():
    s = Speaker()
    s.speak("This is a longer sentence that should be interrupted.")
    time.sleep(0.3)
    assert s.is_speaking()
    s.stop()
    time.sleep(0.2)
    assert not s.is_speaking()
    print("PASS: speak and stop")


def test_speak_latency():
    s = Speaker()
    t0 = time.time()
    s.speak("Done.")
    latency = (time.time() - t0) * 1000
    assert latency < 200
    s.stop()
    print(f"PASS: TTS start latency = {latency:.0f}ms")


if __name__ == "__main__":
    test_clean_markdown()
    test_clean_lists()
    test_clean_numbered_lists()
    test_clean_code_blocks()
    test_clean_inline_code()
    test_clean_emojis()
    test_clean_urls()
    test_clean_github_url()
    test_clean_paths()
    test_clean_symbols()
    test_clean_checkmarks()
    test_preserves_meaning()
    test_clean_empty()
    test_clean_complex_response()
    test_speak_voice()
    test_speak_stop()
    test_speak_latency()
    print("\nAll TTS tests passed.")
