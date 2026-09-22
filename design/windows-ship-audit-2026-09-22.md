# Mike Windows — ship audit, 2026-09-22

> **RESOLVED — 114.5s → ~2.5-13s.** The diagnosis below was right about the
> symptoms and wrong about the cause. It concluded this machine had "no GPU
> path" and that only a smaller model could help. Both were false. The
> machine has an Intel Arc iGPU, Ollama found it, and Ollama *discarded* it:
>
> ```
> dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1
> id=0 library=Vulkan name=Vulkan0 description="Intel(R) Graphics"
> ```
>
> One environment variable. Same 9.7B model, no quality traded away.
> See "P0 resolved" at the end for what actually shipped.

Real machine: Intel Core Ultra 5 125U (12C/14T), integrated graphics only, no
discrete GPU, no CUDA. 16GB RAM. This audit is from actually building,
installing, and running the packaged app, not from reading code.

## P0 — Response latency is broken. This is the ship blocker.

**Measured, not guessed.** Live app log, first message of a session:

```
17:01:31.861  user sends "hey mike"
17:01:31.954  GET /api/tags (fast, 93ms)
17:03:26.456  POST /api/chat returns          <- 114.5 SECONDS later
```

Reply was two words: "Hey! What's up?"

A second, isolated test — same model, same 40,960 `num_ctx`, but a 17-token
throwaway prompt with no system prompt/tools — still took 42s wall clock for
a 64-token reply. Ollama's own stats: **4.4 tokens/sec, 100% CPU**
(`ollama ps` confirms `PROCESSOR 100% CPU`). A third test, replicating Mike's
*real* system prompt + all 44 tool schemas (~7,200 prompt tokens, sent via
the structured `tools=` API param — confirmed in
`brain/providers/ollama_provider.py:278`) **did not finish inside 300
seconds.**

**Root cause:** Every number `config/ollama.py` is tuned around was measured
on a Mac with the model resident on GPU (~16 tok/s, see the file's own
comments — "still entirely on GPU"). This Windows machine has no GPU path in
Ollama at all, so it's running a 9.7B Q4 model at CPU speed, with a
40,960-token context and a ~7,200-token prefix (system prompt + 44 tool
schemas, `brain/core_runtime.py:119`, `brain/core_tools.py`) resent every
first message of a session. `brain/hardware.py` has **zero GPU/capability
detection on Windows** — `unified_memory`/`metal` are hardcoded to
Darwin+arm64 only (`brain/hardware.py:103-104`) — so nothing in the app
adapts model or context size to what the machine can actually drive.

The codebase already knows prefix cost matters — there's a real, working
optimization (`brain/core_runtime.py:1271-1309`) that keeps the system
prompt stable and appends volatile context into history instead of
rebuilding the prefix every turn, specifically so Ollama's KV cache carries
forward turn-to-turn. That optimization is real and correct — the problem
is turn *one*, which has no prior cache to extend, and on this hardware
turn one alone can apparently exceed 5 minutes.

### What to check first (before changing anything)

1. **Confirm the follow-up-turn cache reuse actually recovers speed on
   CPU the way it does on GPU.** If turn 2+ in the same conversation is
   fast (per the existing design), the real fix is entirely about turn 1
   (first message after model load / after a context change) — much
   narrower problem than "everything is slow."
2. **Check `ollama ps` / `ollama run --verbose` for iGPU offload.** This
   machine's Intel Graphics might be usable via Ollama's Vulkan backend on
   some versions — untested tonight, cheapest possible win if it works,
   zero product-quality tradeoff.
3. **Time prompt_eval vs eval separately** (both are in every Ollama
   response as `prompt_eval_duration` / `eval_duration`) to know whether
   the bottleneck is processing the long prefix (fixable by shrinking the
   prompt) or generating tokens (fixable only by a smaller/faster model or
   real GPU accel).

### Concrete fix options, cheapest to most invasive

| # | Fix | Effort | Expected impact | Risk |
|---|---|---|---|---|
| 1 | Verify/enable Ollama iGPU (Vulkan) offload | low (config/env only) | could fix everything at once | may not be supported on this Ollama version/hardware |
| 2 | Shrink `NUM_CTX` for Windows (`config/ollama.py:22`), e.g. 40960 → 8192-16384 | low | cuts KV-cache allocation and prefill cost | smaller working context for long tool chains |
| 3 | Reduce the tool schema payload — send only tools relevant to the message instead of all 44 every time | medium | could cut ~5,000 of the ~7,200 prefix tokens on most turns | needs a relevance filter that doesn't break tool-calling reliability |
| 4 | Swap to a smaller model on Windows (3B-class) | medium-high | 2-3x+ decode speed plausible | must re-verify tool-calling reliability — smaller models are commonly worse at this, and Mike is agentic |
| 5 | Make `brain/hardware.py` Windows/GPU-aware and auto-select model+context by measured capability (extends the module's own stated design intent) | high | the architecturally "right" fix | biggest lift, needs real benchmarking per hardware tier |

**Recommendation for tonight if a stronger model is doing the work:** do
#1 and #3 together first — #1 is free if it works, #3 attacks the actual
measured bottleneck (a 7,200-token prefix on a CPU that does ~4-5 tok/s)
without touching model quality. Only reach for #4 (smaller model) if #1+#3
aren't enough, and only after verifying tool-call reliability on whatever
replacement model is chosen — do not assume it, verify it the same way
`config/ollama.py`'s own comments show qwen3.5:9b was verified.

---

## Fixed tonight (uncommitted, in the working tree, tests passing)

- **Icon/branding.** Repo had zero icon assets; PyInstaller spec had no
  `icon=`; packaged exe showed the generic Python icon. Found Mike's real
  mark is already live as huddlecode.com's own favicon (verified by reading
  the site's `<link rel="icon">` SVG directly). Generated a proper
  multi-res `.ico` from the same geometry/colors
  (`packaging/generate_icon.py` → `packaging/icon.ico`), wired into
  `packaging/mike.spec` (`EXE(icon=...)`) and `QApplication.setWindowIcon()`
  in `ui/app.py`. Rebuilt and confirmed "Copying icon to EXE" in the
  PyInstaller log.
- **No close button.** The frameless panel (`ui/panel/mike_panel.py`) had no
  click target to dismiss it at all — only an undiscoverable global hotkey.
  Added a real ✕ button in the header (`dismiss_requested` signal → the
  same fade-out `_animate_out()` the hotkey already used).
- **`sleep_now()` had no Windows implementation** (`hostplatform/shell.py`)
  — asking Mike to sleep the PC would throw an unhandled `NotImplementedError`.
  Added `rundll32 powrprof.dll,SetSuspendState`.
- **`ui/instrument/tokens.py`** (used live by the always-visible ambient
  edge strip and the floating quick-invoke line) had `.AppleSystemUIFont`,
  SF Mono/Menlo, and a hardcoded `⌘⇧space` glyph, unconditionally, even on
  Windows — this surface is visible almost any time the main panel is
  hidden. Branched fonts on `platform.system()`, fixed the hotkey text in
  `ui/instrument/invoke.py` to match `ui/panel/mike_panel.py`'s own
  platform-aware hint.
- **Broken test**: `tests/test_activity_finalization.py`'s `FakeWorker`
  mock was missing the `tool_progress` signal added by earlier (also
  uncommitted) work, breaking `_retire_active_worker`. Fixed.

**Already correct, verified (from prior uncommitted session work, confirmed
by reading + testing, not just trusted):** `open_application` via
`os.startfile`, the browser-focus-stealing fix (`_bring_browser_forward`),
Ctrl+Q quit binding (Windows' `QKeySequence.Quit` resolves to a nonsense
"Exit" key), streaming Ollama model-pull progress in the UI, SAPI5 voice
naming instead of hardcoded "Samantha".

**Checked and ruled out as a false alarm:** an automated pass flagged
faster-whisper as missing from the packaged build. Verified directly by
reading the PyInstaller archive (`PyInstaller.archive.readers`) — it's
correctly bundled inside the embedded PYZ archive; the check that flagged
it was comparing against a `site-packages`-style folder layout that
PyInstaller onedir builds don't use for pure-Python packages.

---

## Found, not fixed — real but lower priority than P0

- **Full `pytest` suite crashes** (genuine Windows access violation) after
  ~140 accumulated test-created windows in one process. Reproduced twice,
  at different points depending on which tests ran — consistent with
  native resource (likely GDI handle) exhaustion from tests never fully
  tearing down Qt windows between each other, not a logic bug. Real usage
  only ever creates one `MikeWindow` per process lifetime, so this
  shouldn't hit actual users, but it does mean the suite can't currently
  run clean start-to-finish — worth fixing the test fixtures (explicit
  `deleteLater()` + `processEvents()` between window-creating tests, or
  running window-heavy test files in separate pytest-forked processes).
- **No installer** — release is a zip of a onedir PyInstaller build, no
  NSIS/Inno/MSIX, no Start Menu shortcut, no launch-at-login. The product
  blueprint (`design/mike-professional-product-blueprint.md:460`) lists an
  installer as part of Windows V1's definition of done; currently not met.
- **No wake word on Windows** (`voice/wake/__init__.py:25-32`, raises
  `WakeWordUnavailable` explicitly) — honest, non-crashing, but confirm the
  settings UI doesn't offer a wake-word toggle that silently does nothing.
- **No scroll/drag in computer control on Windows**
  (`computer/windows.py:452-472`) — tried, verified broken against real
  apps, pulled back rather than shipped fake. Real functional gap for
  "computer control actually performing actions."
- **`tools/filesystem/path_utils.py`** — flagged by an earlier audit for
  `Movies` vs Windows' `Videos`, and OneDrive-redirected folders meaning
  `~/Desktop` isn't always the real Desktop. Not re-verified this session.
- **`google-genai` dependency** still present in `requirements.txt` despite
  an earlier audit calling it dead weight — not reverified.

---

## Everything already solid, no action needed

Memory (`brain/memory_store.py`) and vision (`vision/screenshot.py`,
`vision/analyzer.py`) are fully OS-agnostic already — no Darwin/Windows
branching anywhere in either. Global hotkey (`hostplatform/desktop.py`) is
genuinely Windows-native (`RegisterHotKey` via ctypes, not an accessibility
API dependency). Close/quit/restart semantics (hide-on-close, tray-only
real quit, `aboutToQuit` teardown) are correct and already resolve a gap
the product blueprint had flagged as open. DPI-aware screen capture
(`hostplatform/capture.py`) reasons explicitly about matching UI
Automation's coordinate space, verified on a 200%-scaled machine per its
own comments.

---

## P0 resolved — what actually fixed it

**Measured, same machine, same model, same prompt:**

```
before                      114.5s   ("hey mike" -> "Hey! What's up?")
after, warm, on the iGPU       2.5s   ("what is 2+2")
                              13.8s   (a fresh question, full prefill)
```

`ollama ps` now reads `100% GPU · 40960 context · UNTIL Forever`, where it
previously read `100% CPU · UNTIL 5 minutes`.

### The actual root cause

Ollama detected the Intel Arc iGPU through its own Vulkan backend and threw
it away, because it skips integrated GPUs by default. `OLLAMA_VULKAN` was
already `true`; `OLLAMA_IGPU_ENABLE` was unset. Nothing surfaced that
decision — Mike just ran a 9.7B model on the CPU forever.

That default is defensible for a server, which cannot know whether a given
iGPU beats its CPU. It is the wrong default for a local assistant on a
laptop, which is *precisely* the machine that has an iGPU and no alternative.

The earlier diagnosis missed this by reasoning from `ollama ps` saying
"100% CPU" to "this machine has no GPU", instead of asking why. The lesson
worth keeping: "the accelerator is not being used" and "there is no
accelerator" look identical from the outside and are entirely different
problems.

### What shipped

- **`brain/accelerator.py`** (new) — persists `OLLAMA_IGPU_ENABLE=1` at user
  scope so it survives reboots and applies however the user next starts
  Ollama, and reports what is *actually* running the model by asking Ollama
  rather than inferring it from what silicon exists.
- **`brain/hardware.py`** — real `gpu_offload` and `discrete_gpu` detection
  (CUDA/ROCm by driver tool, integrated by Vulkan runtime, Metal on Mac).
  Both are round-tripped through `as_dict()`; the first version wasn't, so
  detection reported a GPU and one call later reported none.
- **`config/ollama.py`** — context is now a measurement per machine class,
  with a documented floor (`MIN_NUM_CTX`), plus `KEEP_ALIVE` so the model
  stays resident instead of being evicted every 5 idle minutes and reloaded
  (6.3GB off disk) on the next question.
- **`CoreRuntime.warm()`** — pays the ~7,200-token prefix once at startup on
  a background thread, so the user's first question extends a warm cache
  instead of building one.
- **`tests/test_accelerator_tiers.py`** (new) — asserts every machine class
  keeps Mike's whole toolset.

### The near-miss worth recording

Sizing the context down to 8,192 made things faster and quietly broke Mike.
Only 0.75 of `num_ctx` is usable, so 8,192 left 6,144 tokens for a
~7,200-token prefix, and context planning did exactly what it is designed to
do: dropped tools to make it fit. The log line was
`Context pressure: offering 14 of 44 tools`.

Faster, and missing two thirds of what Mike can do — shipped to the users on
the weakest hardware, who would never have known what they were missing.
`test_model_agnostic` caught it. Hence `MIN_NUM_CTX`, and hence the rule the
new tier tests pin down: **hardware decides how fast Mike is, never how
capable he is.**

### Still true, still unfixed

The tool schemas are ~5,400 of the ~7,200-token prefix and are re-sent every
turn. On the GPU that is now affordable; on a genuinely CPU-only machine it
remains the dominant cost, and sending only relevant tools is the obvious
next lever. The `MIN_NUM_CTX` floor means such a machine is slow rather than
crippled, which is the right trade, but it is still slow.
