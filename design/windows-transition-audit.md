# Mike — cross-platform architecture audit

Written before any Windows code. Everything below was verified against the
tree at `a5a340e` by reading and running it, not inferred from memory. Where I
am proposing rather than reporting, it says so.

The finding that shapes the whole plan: **Mike is not one codebase with a
macOS problem. It is one genuinely portable core with four macOS-shaped holes
in it, plus about a dozen small leaks.** The `computer/` package already has
exactly the architecture this transition needs. Nothing else does.

---

## 1. Current Mac baseline (Phase 0)

| | |
|---|---|
| Commit | `a5a340e`, branch `phase-2-certified`, pushed, tree clean |
| Python | 3.13.7 (venv) |
| Tests | **470 passed, 16 skipped** — every skip is `drives_real_apps`, opt-in via `MIKE_RUN_APP_E2E=1` |
| Brain | Ollama `qwen3.5:9b`, `num_ctx=40960`, usable input 30,720, `num_predict=8192` |
| Voice out | `qwen` provider (Ryan, Qwen3-TTS 0.6B 4-bit, MLX) → `native` (`say`, Samantha) fallback |
| Voice in | `sounddevice`/`soundfile` recorder → `SFSpeechRecognizer` → `NSSpeechRecognizer` wake word |
| UI | PySide6 6.11.1, frameless `Qt.Tool` panel + `QSystemTrayIcon` |
| Storage | `~/Library/Application Support/Mike` — constructed independently in **8 files** |
| Hotkey | Carbon `RegisterEventHotKey`, ⌘⇧Space |

Code volume: `ui` 12,067 lines · `brain` 7,122 · `tools` 5,357 · `voice` 2,276 ·
`computer` 1,456 · `ide` 583 · `config` 251 · `vision` 133 · `auth` 92.

---

## 2. Platform-specific dependencies

### 2a. Python packages

**macOS-only — these make `requirements.txt` uninstallable on Windows as it stands:**
`pyobjc-core`, `pyobjc-framework-Cocoa`, `pyobjc-framework-Speech`,
`pyobjc-framework-AVFoundation`.

**Genuinely cross-platform:** PySide6, numpy, pillow, sounddevice, soundfile,
requests, cryptography, ollama, openpyxl, google-auth stack.

**Dead — imported by zero files, verified:** `customtkinter`, `darkdetect`,
`openai`, `groq`, `google-genai`. (`brain/providers/openai_compatible.py` uses
`requests` directly, not the `openai` package.) These are pure install weight.

**Not in `requirements.txt` at all, by design:** `mlx-audio` and the TTS model
live in a separate interpreter under `~/.mike-tts-bench`. Apple-Silicon-only,
and correctly isolated already.

### 2b. Native APIs, by file

| File | API | Verdict |
|---|---|---|
| `computer/macos.py` | AXUIElement, CGEvent, NSWorkspace, Quartz (61 refs) | Correct — behind the adapter |
| `ui/system/global_hotkey.py` | Carbon `RegisterEventHotKey` | Needs Windows adapter |
| `voice/transcriber.py` | `SFSpeechRecognizer` | Needs Windows adapter |
| `voice/wake_word.py` | `NSSpeechRecognizer` | Needs Windows adapter |
| `voice/providers/native.py` | `say` | Needs Windows adapter |
| `voice/providers/qwen.py` | `afplay` | Needs Windows adapter |
| `vision/screenshot.py` | `screencapture` | Needs Windows adapter |
| `brain/environment.py` | `osascript` | Needs Windows adapter |
| `ui/home/motion.py` | `defaults read` (reduced motion) | Needs Windows adapter |
| `tools/system/actions.py` | `open`, `pmset` (5 branches) | Leak — see §4 |
| `tools/browser/open_*.py` | `open` (2 branches) | Leak — see §4 |
| `tools/terminal/actions.py` | `os.killpg`, `os.getpgid`, `start_new_session` | Leak + real bug — see §4 |

---

## 3. Current abstraction boundaries

Three exist and are sound. They are the template for everything else.

**`computer/base.py` → `computer/macos.py`.** Canonical types (`UIElement`,
`WindowInfo`, `Observation`, `ActionResult`, `Bounds`), a ten-method ABC, and
`get_controller()` which dispatches on `platform.system()` and — importantly —
**raises an explanatory `ComputerError` on Windows rather than returning a
stub**. The docstring already states the rule: *"Nothing above this file
mentions CGEvent, AXUIElement, UIAutomation or XTest."* I checked: it holds.

**`voice/providers/base.py` → `native.py` / `qwen.py`.** A real provider
contract with an explicit `available() -> (bool, why)` and a fail-to-native
rule. This is why the Windows TTS work is additive rather than surgical.

**`brain/providers/` → ollama / openai-compatible.** Model access is already
provider-shaped and hardware-aware via `brain/hardware.py`.

The contract Windows must satisfy for computer control:

```
observe(app, limit) -> Observation      list_windows() -> [WindowInfo]
frontmost_app() -> str|None             running_apps() -> [str]
click(x, y, button, count)              scroll(dx, dy, x, y)
drag(from_x, from_y, to_x, to_y)        type_text(text)
press_keys(key, modifiers)              activate_app(name)
```

---

## 4. Abstraction leaks

These are the actual work of Phase 1–2. Ordered by how much damage each does.

**L1 — Storage root duplicated 8 times.** `Path.home()/"Library"/"Application
Support"/"Mike"` is independently rebuilt in `config/preferences.py`,
`brain/memory_store.py`, `revert_store.py`, `situation_store.py`,
`activity_store.py`, `projects.py`, `capability_probe.py`,
`voice/providers/qwen.py`. This is the same second-hardcoded-copy shape the
repo has been bitten by twice before (`NUM_CTX`, `OLLAMA_MODEL`). One
platform-aware storage module, eight call sites deleted.

**L2 — Three persistent paths are relative to the working directory.** Not a
Windows issue; a bug everywhere, which Windows will simply make fatal:

- `logs/logger.py:3` → `os.makedirs("logs")`, `logs/mike.log`
- `voice/recorder.py:18` → `Path("audio/recordings")`
- `auth/token_store.py:3` → `"storage/token.json"` ← **the OAuth token**

All three write wherever Mike was launched from. That is why empty `logs/`,
`audio/`, `storage/` directories sit in the repo root. On Windows, an installed
app's CWD is frequently not writable. The OAuth one also means the most
sensitive file Mike holds is stored next to the source, in plaintext.

**L3 — `os.killpg` in `tools/terminal/actions.py:313`.** Background processes
are started with `start_new_session=True` (POSIX-only) and stopped by killing
the process group. On Windows `os.killpg`/`os.getpgid` do not exist; the
`except Exception` catches the `AttributeError` and falls through to
`process.terminate()`, which does **not** kill children. So it will not crash —
it will silently leak every child a background command spawned. Phase 9 names
"no child-process leaks" as a requirement; this is where it breaks. Windows
needs a Job Object, or `taskkill /T /F`.

**L4 — `platform.system()` branching in high-level code.** `tools/system/actions.py`
(5 sites) and `tools/browser/open_browser.py` / `open_url.py` (2 sites) already
contain `if Darwin: ... elif Windows: ...` with shell commands inline. This is
precisely the shape Phase 2 forbids — a *tool* deciding how the OS opens a
browser. Note `open_browser.py` already has an unverified Windows branch
(`start`, `shell=True`); it is untested and I would not trust it.

**L5 — `vision/screenshot.py` has no seam.** The `Screenshot` class *is* the
macOS implementation. It also does no DPI handling at all — there is no
`devicePixelRatio` or HiDPI reference anywhere in `ui/`.

**L6 — Apple font stacks in `ui/panel/style.py`.** `-apple-system,
BlinkMacSystemFont, 'SF Pro Text'` and `SF Mono, Menlo`. On Windows every one
of these misses and Mike renders in a generic fallback rather than Segoe UI.

**L7 — `tools/filesystem/path_utils.py` assumes home-relative user folders.**
`Path.home()/"Desktop"` etc. Mostly correct on Windows, with two real problems:
`Movies` is `Videos` on Windows, and OneDrive-redirected folders mean
`~/Desktop` is frequently *not* the user's Desktop. Windows wants
`SHGetKnownFolderPath`.

---

## 5. Required Windows adapters

| Capability | Windows technology I intend to use | Notes |
|---|---|---|
| Computer control | **UI Automation** (UIAutomationCore) via `comtypes`, with `uiautomation` or a thin direct wrapper | The real work. Maps well onto `observe`/`click`/`type_text` |
| Window enumeration / focus | Win32 `EnumWindows`, `SetForegroundWindow`, `AttachThreadInput` | `SetForegroundWindow` has foreground-lock rules; needs care |
| Input synthesis | `SendInput` (not `keybd_event`) | UIA `Invoke()` preferred where the pattern exists |
| Screen capture | Windows.Graphics.Capture, or `BitBlt`/`PrintWindow` fallback | Must be DPI-aware; see §12 |
| Global hotkey | `RegisterHotKey` + a message pump | Win+Space is taken by IME; needs a different binding |
| TTS | SAPI5 / `Windows.Media.SpeechSynthesis` | Becomes the always-available fallback, replacing `say` |
| Audio playback | `sounddevice` (already a dependency) | Replaces `afplay`; also removes a process spawn per chunk |
| STT | Whisper (local) or Windows Speech | `SFSpeechRecognizer` has no Windows analogue |
| Wake word | openWakeWord or equivalent | `NSSpeechRecognizer` has no analogue |
| Frontmost app | `GetForegroundWindow` + `GetWindowThreadProcessId` | Replaces `osascript` |
| Process lifecycle | Job Objects / `CREATE_NEW_PROCESS_GROUP` | Fixes L3 |
| Storage root | `%LOCALAPPDATA%\Mike` | Fixes L1 |
| Reduced motion | `SystemParametersInfo(SPI_GETCLIENTAREAANIMATION)` | Replaces `defaults read` |

**TTS engine note.** MLX is Apple-Silicon-only, so Qwen3-TTS as it exists today
does not cross. The decision the architecture must preserve is that the *voice
engine* and the *OS audio path* are separate: Phase 7 is right. On Windows the
neural option is ONNX Runtime (Piper/Kokoro class) with SAPI5 as the guaranteed
fallback — the same "never go silent" rule `Speaker` already enforces.

---

## 6. What stays shared (do not touch)

`brain/` in full — runtime, providers, context budget, the conversation-window
trimming and prompt-prefix work from this session, memory, situation, activity,
revert, projects. `tools/` protocol and dispatch. Safety gating and the
fail-closed confirmation path. `core/tool_executor.py`. The `UIController`
contract. `ide/` (a localhost socket; already neutral). SQLite concurrency
hardening in `brain/_local_db.py`. The Summoned Presence design language.

**Explicitly: no Windows conditional may enter any of these.**

---

## 7. What becomes a platform service

New `platform/` package, same shape as `computer/`: an ABC plus per-OS
implementations plus a `get_*()` that raises honestly.

- `platform/storage.py` — data root, logs, cache, temp (absorbs L1, L2)
- `platform/capture.py` — screen capture (absorbs L5)
- `platform/desktop.py` — tray, notifications, hotkey, reduced motion, frontmost app (absorbs L4, L6)
- `platform/processes.py` — spawn, terminate-tree, cleanup (absorbs L3)
- `platform/shell.py` — open URL / file / application (absorbs L4)
- `voice/providers/windows.py` — SAPI5, beside `native.py`
- `voice/input/` — recorder stays shared; transcriber and wake word become adapters
- `computer/windows.py` — the UIA implementation

---

## 8. Dependency changes

Add `sys_platform` markers so each OS installs only what it can:

```
pyobjc-core==12.2.2                  ; sys_platform == "darwin"
pyobjc-framework-Cocoa==12.2.2       ; sys_platform == "darwin"
pyobjc-framework-Speech==12.2.2      ; sys_platform == "darwin"
pyobjc-framework-AVFoundation==12.2.2; sys_platform == "darwin"
comtypes                             ; sys_platform == "win32"
pywin32                              ; sys_platform == "win32"
```

Remove the five dead packages (§2a). Keep every optional subsystem behind the
existing "one missing dependency must not kill startup" rule — that principle
already exists and must survive.

---

## 9. Testing strategy

Three layers, matching Phase 16:

1. **Platform-independent** — the current 470. These must pass on Windows
   unchanged. Any that fail are, by definition, leaks I missed; that failure
   list is the real audit result and I expect it to be non-empty.
2. **Adapter conformance** — one shared suite run against whichever adapter
   the host provides, asserting the *contract* (`observe()` returns addressable
   elements; `press_keys` reports honestly; unimplemented raises rather than
   returns success). Same tests, both platforms.
3. **Real-app E2E** — gated like `MIKE_RUN_APP_E2E` is today, against Explorer,
   Edge, Chrome, VS Code, Word, Excel.

**Do not weaken a test to make it cross-platform.** A macOS test that cannot
apply gets skipped with a reason, the way `drives_real_apps` already works.

---

## 10. Migration order

Everything through step 5 is Mac-side refactoring, verified by the existing 470
tests before any Windows machine is involved.

1. `platform/storage.py`; delete the 8 duplicated roots; fix the 3 relative paths
2. `platform/processes.py`; fix `os.killpg` (fixes a latent Mac bug too)
3. `platform/shell.py` + `capture.py`; empty `tools/` of platform branches
4. `platform/desktop.py`; hotkey and frontmost-app behind it
5. Voice input split: engine vs OS audio
6. **Re-run the 470. This is the gate.**
7. → Windows machine. Phase 18 order: startup → storage → tray → hotkey →
   window → mic → TTS → capture → windows/focus → UIA → input → dialogs →
   browser → Explorer → Word → Excel → VS Code → workflows → endurance
8. Capability contract (Phase 22) filled in from verified results only

---

## 11. Risks

**Highest — UIA is not AX.** The macOS adapter is 1,456 lines against a mature
accessibility tree. UIA is a different model (patterns vs attributes), is
slower to traverse, and Electron apps (VS Code) expose an incomplete tree
unless accessibility is switched on. **VS Code and Chrome are the two most
likely to disappoint.** I would validate those two before promising Phase 19.

**High — the hotkey.** `RegisterHotKey` fails silently if another process owns
the combination, and cannot be captured over elevated windows without matching
elevation. ⌘⇧Space has no clean Windows twin.

**High — DPI.** There is currently *no* DPI handling. Windows fractional
scaling plus mixed-DPI multi-monitor is the classic way coordinate systems go
quietly wrong. Capture and click must share one coordinate space, asserted by a
test, not by inspection.

**Medium — the TTS story regresses.** The 0-gap jitter buffer and the worker
cancel protocol are *design*, and they port; the Qwen engine does not. Windows
starts on SAPI5, which will sound worse than Ryan. That should be stated to the
user, not hidden.

**Medium — hardware.** `brain/hardware.py` detects unified memory and Metal and
degrades honestly elsewhere, but has no VRAM or CUDA/DirectML detection. On a
Windows laptop with a discrete GPU, "what can this machine actually run" is
currently unanswerable. Phase 13 needs that gap closed.

**Low but real — Qt on Windows.** Frameless + translucent + always-on-top is
supported but shadows, focus stealing and taskbar behaviour differ. The
Summoned Presence will need real tuning, not a recompile.

---

## 12. Things that should NOT change

- The `computer/base.py` contract and canonical types. Windows conforms to it.
- The fail-closed confirmation gate. Platform-independent, non-negotiable.
- `Speaker`'s never-go-silent fallback rule.
- SQLite concurrency hardening.
- The conversation-window and prompt-prefix architecture from this session.
- `MAX_AGENT_STEPS = 20` — still an open question, still deliberately not raised.
- The Summoned Presence interaction model.
- The habit of raising an explanatory error instead of returning a stub.

---

## 13. Open question for you

`get_controller()` raising on Windows is correct today. Once `computer/windows.py`
exists but is *partial*, the honest choice is per-capability: `observe()` works,
`drag()` raises `NotSupportedError` naming the gap. That means Mike will
sometimes say "I can see the window but I can't drag on Windows yet."

I think that is right, and better than a silent no-op. Confirm before I build
it that way, because it changes what Mike says out loud to you.
