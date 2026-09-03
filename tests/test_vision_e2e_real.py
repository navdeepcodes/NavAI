"""Real end-to-end vision tests — no mocks, real screen, real models.

Exercises CoreRuntime.process_streaming() with actual Ollama calls.
"""
from __future__ import annotations

import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.core_runtime import CoreRuntime
from vision.vision import Vision
from vision.screenshot import Screenshot


def timed(label, fn):
    t0 = time.time()
    result = fn()
    elapsed = time.time() - t0
    print(f"  [{label}] {elapsed:.1f}s")
    return result, elapsed


def collect_stream(runtime, message):
    """Run process_streaming and collect all events with timings."""
    events = []
    full_text = ""
    tool_started = False
    tool_ended = False
    t0 = time.time()

    for event_type, payload in runtime.process_streaming(message):
        elapsed = time.time() - t0
        events.append((event_type, payload, elapsed))

        if event_type == "token":
            full_text += payload
        elif event_type == "tool_start":
            tool_started = True
            print(f"  [tool_start @ {elapsed:.1f}s] {payload}")
        elif event_type == "tool_end":
            tool_ended = True
            print(f"  [tool_end   @ {elapsed:.1f}s] {payload[:100]}")

    total = time.time() - t0
    return {
        "events": events,
        "text": full_text.strip(),
        "tool_started": tool_started,
        "tool_ended": tool_ended,
        "total_time": total,
    }


def test_screenshot_capture():
    """Verify raw screenshot capture works."""
    print("\n--- Pre-check: Screenshot Capture ---")
    ss = Screenshot()
    (path, cap_time) = timed("capture", ss.capture)
    assert os.path.exists(path), f"Screenshot file missing: {path}"
    size = os.path.getsize(path)
    print(f"  File: {path} ({size / 1024:.0f} KB)")
    assert size > 10_000, f"Screenshot too small ({size} bytes) — likely blank"
    return path, cap_time


def test_vision_model_direct(image_path):
    """Verify qwen2.5vl:3b can analyze a screenshot directly."""
    print("\n--- Pre-check: Vision Model Direct ---")
    from vision.analyzer import VisionAnalyzer
    analyzer = VisionAnalyzer()
    (desc, inf_time) = timed("inference", lambda: analyzer.analyze(image_path))
    print(f"  Description: {desc[:200]}")
    assert len(desc) > 20, f"Vision description too short: {desc!r}"
    return desc, inf_time


def test1_screen_understanding(runtime):
    """Test 1: Basic screen understanding via full pipeline."""
    print("\n========== TEST 1: Screen Understanding ==========")
    result = collect_stream(
        runtime,
        "Look at my screen and tell me what application I'm currently using.",
    )
    print(f"  Response: {result['text'][:300]}")
    print(f"  Total: {result['total_time']:.1f}s")

    assert result["tool_started"], "FAIL: see_screen tool was NOT called"
    assert result["tool_ended"], "FAIL: see_screen tool did not complete"
    assert len(result["text"]) > 10, "FAIL: Empty or too-short response"

    found_tool = any(
        "Looking at your screen" in ev[1]
        for ev in result["events"]
        if ev[0] == "tool_start"
    )
    assert found_tool, "FAIL: Tool start was not 'Looking at your screen'"

    return result


def test2_visible_text(runtime):
    """Test 2: Read visible text from screen."""
    print("\n========== TEST 2: Visible Text ==========")
    print("  (Note: 'MIKE VISION TEST 8472' must be visible on screen)")
    result = collect_stream(
        runtime,
        "Look at my screen. Can you see any text that says 'MIKE VISION TEST' followed by a number? What is the full text?",
    )
    print(f"  Response: {result['text'][:300]}")
    print(f"  Total: {result['total_time']:.1f}s")

    assert result["tool_started"], "FAIL: see_screen was NOT called"
    return result


def test3_ui_understanding(runtime):
    """Test 3: Describe what's on screen."""
    print("\n========== TEST 3: UI Understanding ==========")
    result = collect_stream(
        runtime,
        "Look at my screen and describe what I'm currently looking at. Be specific about what you see.",
    )
    print(f"  Response: {result['text'][:400]}")
    print(f"  Total: {result['total_time']:.1f}s")

    assert result["tool_started"], "FAIL: see_screen was NOT called"
    assert len(result["text"]) > 30, "FAIL: Description too short"
    return result


def test4_visible_error(runtime):
    """Test 4: Identify an error on screen."""
    print("\n========== TEST 4: Visible Error ==========")
    print("  (Note: an error or warning should be visible on screen)")
    result = collect_stream(
        runtime,
        "Look at my screen. Is there any error message or warning visible? Describe it.",
    )
    print(f"  Response: {result['text'][:300]}")
    print(f"  Total: {result['total_time']:.1f}s")

    assert result["tool_started"], "FAIL: see_screen was NOT called"
    return result


def test5_normal_conversation(runtime):
    """Test 5: Normal chat must NOT trigger vision."""
    print("\n========== TEST 5: Normal Conversation (NO vision) ==========")
    result = collect_stream(runtime, "How are you?")
    print(f"  Response: {result['text'][:200]}")
    print(f"  Total: {result['total_time']:.1f}s")

    assert not result["tool_started"], "FAIL: see_screen was triggered on casual chat!"
    assert len(result["text"]) > 5, "FAIL: Empty response"

    vision_events = [
        ev for ev in result["events"]
        if ev[0] == "tool_start" and "screen" in ev[1].lower()
    ]
    assert len(vision_events) == 0, "FAIL: Vision tool appeared in events"
    return result


def test6_vision_plus_action(runtime):
    """Test 6: Vision + regular tool coexist."""
    print("\n========== TEST 6: Vision + Action ==========")

    print("  Step A: Vision call")
    result_a = collect_stream(
        runtime,
        "Look at my screen and tell me what website or app is open.",
    )
    print(f"  Response A: {result_a['text'][:200]}")

    assert result_a["tool_started"], "FAIL: Vision not triggered"

    print("\n  Step B: Regular tool call (browser)")
    result_b = collect_stream(
        runtime,
        "Open YouTube.",
    )
    print(f"  Response B: {result_b['text'][:200]}")

    assert result_b["tool_started"], "FAIL: Browser tool not triggered"

    b_vision = any(
        "Looking at your screen" in ev[1]
        for ev in result_b["events"]
        if ev[0] == "tool_start"
    )
    assert not b_vision, "FAIL: Vision triggered on browser action"

    return result_a, result_b


def security_check():
    """Verify the vision pipeline is local-only."""
    print("\n========== SECURITY CHECK ==========")

    import inspect
    from vision.analyzer import VisionAnalyzer

    source = inspect.getsource(VisionAnalyzer)

    for cloud in ["gemini", "openrouter", "groq", "openai.com", "googleapis", "cloud"]:
        assert cloud not in source.lower(), f"FAIL: Found '{cloud}' in VisionAnalyzer source"

    print("  VisionAnalyzer source: no cloud provider references")

    from config.ollama import OLLAMA_HOST, OLLAMA_VISION_MODEL
    assert "127.0.0.1" in OLLAMA_HOST or "localhost" in OLLAMA_HOST, \
        f"FAIL: OLLAMA_HOST is not local: {OLLAMA_HOST}"
    print(f"  OLLAMA_HOST: {OLLAMA_HOST}")
    print(f"  OLLAMA_VISION_MODEL: {OLLAMA_VISION_MODEL}")

    from brain.core_runtime import CoreRuntime
    source_rt = inspect.getsource(CoreRuntime._execute_vision)
    assert "Vision()" in source_rt, "FAIL: _execute_vision doesn't use Vision class"
    for cloud in ["gemini", "openrouter", "groq"]:
        assert cloud not in source_rt.lower(), f"FAIL: Found '{cloud}' in _execute_vision"

    print("  _execute_vision: local Vision class only")
    print("  PASS: All processing is Mac → local Ollama → qwen2.5vl:3b")


if __name__ == "__main__":
    print("=" * 60)
    print("MIKE VISION — REAL END-TO-END TESTS")
    print("=" * 60)

    timings = {}

    # Pre-checks
    img_path, cap_time = test_screenshot_capture()
    timings["screenshot_capture"] = cap_time

    desc, inf_time = test_vision_model_direct(img_path)
    timings["vision_inference"] = inf_time

    security_check()

    # Initialize runtime (real Ollama connection)
    print("\n--- Initializing CoreRuntime ---")
    runtime = CoreRuntime()
    print("  Ready.")

    results = {}

    # Test 5 first (fast, no vision)
    results["5_normal"] = test5_normal_conversation(runtime)

    # Vision tests
    results["1_screen"] = test1_screen_understanding(runtime)
    results["3_ui"] = test3_ui_understanding(runtime)

    # Test 2 needs visible text — run it but don't fail hard
    results["2_text"] = test2_visible_text(runtime)

    # Test 4 — error detection
    results["4_error"] = test4_visible_error(runtime)

    # Test 6 — vision + action coexist
    results["6_combined"] = test6_vision_plus_action(runtime)

    # Summary
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"  Screenshot capture:     {timings['screenshot_capture']:.1f}s")
    print(f"  Vision inference:       {timings['vision_inference']:.1f}s")
    print(f"  Total vision latency:   {timings['screenshot_capture'] + timings['vision_inference']:.1f}s")

    for key, r in results.items():
        if isinstance(r, tuple):
            for i, sub in enumerate(r):
                print(f"  {key}[{i}] total:        {sub['total_time']:.1f}s")
        else:
            print(f"  {key} total:            {r['total_time']:.1f}s")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)

    # Clean up screenshot
    if os.path.exists(img_path):
        os.unlink(img_path)
