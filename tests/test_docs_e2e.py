"""Real end-to-end document + code tests via Ollama."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — must run before any brain/config import

from brain.core_runtime import CoreRuntime


def collect(runtime, message):
    events = []
    full_text = ""
    tools_used = []
    t0 = time.time()

    for event_type, payload in runtime.process_streaming(message):
        events.append((event_type, payload))
        if event_type == "token":
            full_text += payload
        elif event_type == "tool_start":
            tools_used.append(payload)
            print(f"  [tool] {payload}")
        elif event_type == "tool_end":
            print(f"  [done] {payload[:120]}")

    total = time.time() - t0
    return {"text": full_text.strip(), "tools": tools_used, "time": total}


if __name__ == "__main__":
    runtime = CoreRuntime()

    print("=" * 60)
    print("DOCUMENTS + CODE — REAL E2E BENCHMARK")
    print("=" * 60)

    # --- TEST 1: Read a real PDF ---
    print("\n========== TEST 1: Read PDF ==========")
    r = collect(runtime, "Read the PDF file at ~/Downloads/Motor Specifications (2).pdf and give me a one-sentence summary of what it's about.")
    print(f"  Response: {r['text'][:300]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")
    pdf_ok = any("document" in t.lower() or "reading" in t.lower() for t in r["tools"])
    print(f"  Used read_document: {pdf_ok}")

    # --- TEST 2: Read a DOCX ---
    print("\n========== TEST 2: Read DOCX ==========")
    r = collect(runtime, "What is the file ~/Downloads/Webpage content (1).docx about? Summarize in one sentence.")
    print(f"  Response: {r['text'][:300]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")

    # --- TEST 3: Read a code file and explain ---
    print("\n========== TEST 3: Explain Code ==========")
    r = collect(runtime, "Read the file at ~/Developer/NavAI-v0/brain/core_tools.py and tell me how many tools are defined in it.")
    print(f"  Response: {r['text'][:300]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")

    # --- TEST 4: Search files ---
    print("\n========== TEST 4: Search Files ==========")
    r = collect(runtime, "Find all Python files in ~/Developer/NavAI-v0/brain/ that mention 'DISPATCH'.")
    print(f"  Response: {r['text'][:300]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")

    # --- TEST 5: Multi-step code task ---
    print("\n========== TEST 5: Multi-step Code Task ==========")
    test_file = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w")
    test_file.write("def add(a, b):\n    return a - b  # BUG: should be +\n")
    test_file.close()
    r = collect(runtime, f"Read the file {test_file.name}, find any bugs, and explain what's wrong.")
    print(f"  Response: {r['text'][:400]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")
    bug_found = "+" in r["text"] or "add" in r["text"].lower() or "subtract" in r["text"].lower() or "minus" in r["text"].lower()
    print(f"  Bug identified: {bug_found}")
    os.unlink(test_file.name)

    # --- TEST 6: Normal conversation (no tools) ---
    print("\n========== TEST 6: Normal Chat ==========")
    r = collect(runtime, "What's the capital of France?")
    print(f"  Response: {r['text'][:200]}")
    print(f"  Tools used: {r['tools']}")
    print(f"  Time: {r['time']:.1f}s")
    assert len(r["tools"]) == 0, "Tools should NOT trigger on casual chat"
    print(f"  No tools triggered: True")

    print("\n" + "=" * 60)
    print("ALL E2E TESTS COMPLETE")
    print("=" * 60)
