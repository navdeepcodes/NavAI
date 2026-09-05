"""Real end-to-end vision tests with qwen2.5vl-16k:latest.

Separates pipeline correctness from perception accuracy.
"""
from __future__ import annotations

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import

from brain.core_runtime import CoreRuntime
from config.ollama import OLLAMA_VISION_MODEL


def collect_stream(runtime, message):
    events = []
    full_text = ""
    tool_started = False
    tool_ended = False
    tool_result_raw = ""
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
            tool_result_raw = payload
            print(f"  [tool_end   @ {elapsed:.1f}s] {payload[:150]}")

    total = time.time() - t0
    return {
        "events": events,
        "text": full_text.strip(),
        "tool_started": tool_started,
        "tool_ended": tool_ended,
        "tool_result": tool_result_raw,
        "total_time": total,
    }


def vision_latency(events):
    """Extract vision-only latency (tool_start to tool_end)."""
    start = end = None
    for etype, _, t in events:
        if etype == "tool_start" and start is None:
            start = t
        if etype == "tool_end":
            end = t
    if start is not None and end is not None:
        return end - start
    return None


if __name__ == "__main__":
    print("=" * 60)
    print(f"VISION MODEL COMPARISON: {OLLAMA_VISION_MODEL}")
    print("=" * 60)

    runtime = CoreRuntime()
    results = {}

    # --- TEST 1: App Identification ---
    print("\n========== TEST 1: App Identification ==========")
    print("  Expected: TextEdit (frontmost app with test text)")
    r = collect_stream(
        runtime,
        "Look at my screen and tell me what application I'm currently using. "
        "Be specific about the exact app name.",
    )
    vlat = vision_latency(r["events"])
    print(f"  Vision latency: {vlat:.1f}s" if vlat else "  Vision latency: N/A")
    print(f"  Total round-trip: {r['total_time']:.1f}s")
    print(f"  Pipeline: {'OK' if r['tool_started'] and r['tool_ended'] else 'FAIL'}")
    print(f"  Final response: {r['text'][:400]}")
    print(f"  Vision model raw (first 300): {r['tool_result'][:300]}")
    results["1_app"] = r

    # --- TEST 2: Visible Text / OCR ---
    print("\n========== TEST 2: Read Visible Text ==========")
    print("  Expected: MIKE VISION TEST 8472")
    r = collect_stream(
        runtime,
        "Look at my screen. There should be text visible that says 'MIKE VISION TEST' "
        "followed by a number. Read the exact full text including the number.",
    )
    vlat = vision_latency(r["events"])
    print(f"  Vision latency: {vlat:.1f}s" if vlat else "  Vision latency: N/A")
    print(f"  Total round-trip: {r['total_time']:.1f}s")
    print(f"  Pipeline: {'OK' if r['tool_started'] and r['tool_ended'] else 'FAIL'}")
    print(f"  Final response: {r['text'][:400]}")
    print(f"  Vision model raw (first 300): {r['tool_result'][:300]}")

    text_lower = r["text"].lower() + r["tool_result"].lower()
    found_8472 = "8472" in text_lower
    found_mike_vision = "mike vision test" in text_lower
    print(f"  Contains '8472': {found_8472}")
    print(f"  Contains 'MIKE VISION TEST': {found_mike_vision}")
    results["2_text"] = r

    # --- TEST 3: Error Identification ---
    print("\n========== TEST 3: Identify Visible Error ==========")
    print("  Expected: 'ERROR: Connection timeout on port 5432'")
    r = collect_stream(
        runtime,
        "Look at my screen. Is there an error message visible? "
        "Read the exact error text.",
    )
    vlat = vision_latency(r["events"])
    print(f"  Vision latency: {vlat:.1f}s" if vlat else "  Vision latency: N/A")
    print(f"  Total round-trip: {r['total_time']:.1f}s")
    print(f"  Pipeline: {'OK' if r['tool_started'] and r['tool_ended'] else 'FAIL'}")
    print(f"  Final response: {r['text'][:400]}")
    print(f"  Vision model raw (first 300): {r['tool_result'][:300]}")

    error_found = any(
        kw in (r["text"].lower() + r["tool_result"].lower())
        for kw in ["5432", "connection timeout", "database unreachable"]
    )
    print(f"  Error content detected: {error_found}")
    results["3_error"] = r

    # --- TEST 4: UI Understanding ---
    print("\n========== TEST 4: Describe Visible UI ==========")
    print("  Expected: Description of TextEdit window with text content")
    r = collect_stream(
        runtime,
        "Look at my screen and describe in detail what UI elements and windows "
        "you can see. What application windows are open?",
    )
    vlat = vision_latency(r["events"])
    print(f"  Vision latency: {vlat:.1f}s" if vlat else "  Vision latency: N/A")
    print(f"  Total round-trip: {r['total_time']:.1f}s")
    print(f"  Pipeline: {'OK' if r['tool_started'] and r['tool_ended'] else 'FAIL'}")
    print(f"  Final response: {r['text'][:500]}")
    print(f"  Vision model raw (first 400): {r['tool_result'][:400]}")
    results["4_ui"] = r

    # --- TEST 5: Normal Conversation (NO vision) ---
    print("\n========== TEST 5: Normal Conversation ==========")
    r = collect_stream(runtime, "How are you?")
    print(f"  Total: {r['total_time']:.1f}s")
    print(f"  Vision triggered: {r['tool_started']}")
    print(f"  Response: {r['text'][:200]}")
    assert not r["tool_started"], "FAIL: Vision triggered on casual chat!"
    results["5_normal"] = r

    # --- SUMMARY ---
    print("\n" + "=" * 60)
    print("LATENCY SUMMARY")
    print("=" * 60)
    for key in ["1_app", "2_text", "3_error", "4_ui"]:
        r = results[key]
        vlat = vision_latency(r["events"])
        print(f"  {key}: vision={vlat:.1f}s, total={r['total_time']:.1f}s" if vlat else f"  {key}: total={r['total_time']:.1f}s")
    print(f"  5_normal: total={results['5_normal']['total_time']:.1f}s (no vision)")

    print("\n" + "=" * 60)
    print(f"ALL TESTS COMPLETE — Model: {OLLAMA_VISION_MODEL}")
    print("=" * 60)
