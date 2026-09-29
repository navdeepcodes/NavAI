# Mike for Windows — what was done, 2026-09-22

Everything below was verified by building, installing and running the real
thing on a real machine — Intel Core Ultra 5 125U, integrated Arc graphics,
no discrete GPU, 15.4GB RAM, Windows 11. Where something is unverified or
unresolved it says so.

---

## 1. The headline: 114.5s → ~13s, same model

**The symptom.** A first message of "hey mike" took **114.5 seconds** to come
back with "Hey! What's up?" (live app log, 17:01:31 → 17:03:26).

**The wrong diagnosis.** The first audit concluded the machine had no GPU
path and that only a smaller, dumber model could help. Both were false.

**The actual cause.** Ollama detected the Intel Arc iGPU through its own
Vulkan backend and then deliberately threw it away, because it skips
integrated GPUs by default:

```
dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1
id=0 library=Vulkan name=Vulkan0 description="Intel(R) Graphics"
```

`OLLAMA_VULKAN` was already true. `OLLAMA_IGPU_ENABLE` was unset. Nothing
surfaced that decision, so Mike ran a 9.7B model on the CPU at 4.4 tok/s
and looked broken.

**Measured after enabling it:**

```
before                          114.5s
after, warm, on the iGPU          2.5s   ("what is 2+2")
                                 13.0s   (a fresh question)
ollama ps:  100% GPU · 40960 context · UNTIL Forever
```

The lesson worth keeping: *"the accelerator is not being used"* and *"there
is no accelerator"* look identical from outside and are entirely different
problems. Reasoning from `ollama ps` saying "100% CPU" straight to "this
machine has no GPU" is what cost the first hour.

### Supporting fixes that shipped with it

- **`brain/accelerator.py`** (new) — persists `OLLAMA_IGPU_ENABLE=1` at user
  scope so every user gets the GPU, not just this machine, and reports what
  is *actually* running the model by asking Ollama rather than inferring it
  from what silicon exists.
- **Model eviction.** `keep_alive` was never set anywhere, so Ollama's
  5-minute default applied. A hotkey-summoned assistant is idle by design,
  so a gap longer than five minutes silently evicted the model and the next
  question paid a full 6.3GB reload *before* prefill. This is why early
  measurements swung between 114s and 490s. Now pinned (`UNTIL Forever`) on
  machines with the RAM for it.
- **Cold prefix.** `CoreRuntime.warm()` pays the ~7,200-token prefix once at
  startup on a background thread, so the first real question extends a warm
  cache instead of building one. Measured 5.7x between cold and warm.

---

## 2. Every Windows machine gets a *whole* Mike

A context reduction made things faster and quietly broke Mike. Only 0.75 of
`num_ctx` is usable, so 8,192 left 6,144 tokens for a ~7,200-token prefix,
and context planning did exactly what it is designed to do — dropped tools
to make it fit:

```
Context pressure: offering 14 of 44 tools to qwen3.5:9b
```

Faster, and missing two thirds of what Mike can do, shipped to the users on
the weakest hardware who would never have known. `test_model_agnostic`
caught it.

Hence `MIN_NUM_CTX`, and the rule `tests/test_accelerator_tiers.py` now
pins down: **hardware decides how fast Mike is, never how capable he is.**

| Machine | Context | Notes |
|---|---|---|
| Apple Silicon (Metal) | 40,960 | unchanged |
| Windows + NVIDIA/AMD discrete | 40,960 | detected by driver tool on PATH |
| Windows + integrated GPU, ≥15GB RAM | 40,960 | verified still `100% GPU` at 6.7/6.7 GB |
| Windows + integrated GPU, less RAM | 24,576 | avoids spilling back to CPU |
| No GPU offload at all | 24,576 | slow, but whole |

---

## 3. Branding

The repo contained **zero icon assets** and the PyInstaller spec had no
`icon=`, so the packaged app showed the generic Python icon.

Mike's real mark was already live as huddlecode.com's own favicon (read
directly from the site's `<link rel="icon">` SVG): a dark rounded square
with three bars, in the same `--ink`/`--paper` tokens `ui/panel/style.py`
already uses. `packaging/generate_icon.py` regenerates
`packaging/icon.ico` from that exact geometry at 7 sizes.

Wired into `EXE(icon=...)` and `QApplication.setWindowIcon()`. **Verified by
extracting the icon back out of the built `Mike.exe`** — not by trusting the
build log.

---

## 4. A real close button

The panel is frameless: no title bar, no OS close box. Before this, the only
way to dismiss it was a global hotkey nobody had been told about. Every
other control on that surface is reached by clicking something; closing was
the one exception.

Added a ✕ in the header, wired to the same fade-out the hotkey already used.

---

## 5. Conversation

The complaint was that Mike "reads like a newspaper, not like a normal
convo".

**The cause was not what I first assumed.** I was confident
`temperature: 0.4` was the culprit and raised it to 0.7. Tested both — they
produced near-identical greetings. It was not the cause. (0.7 kept anyway:
it is what qwen3.5 is built for, and tool-calling verified equal at both.)

**The real cause** was in `clean_for_speech`. It stripped bullet *markers*
but left the list *structure*, so each item arrived as its own clipped,
subjectless line. Read aloud, that is literally a news reader going through
headlines:

```
- Open websites and search the web     ->   Open websites and search the web
- Read and write files                 ->   Read and write files
```

Now a run of items becomes one sentence: *"I can help you with a bunch of
things: open websites and search the web, read and write files, and run
commands in your terminal."*

Also fixed:

- **`core_runtime.py:120` told every Windows user Mike "lives on the user's
  Mac desktop"** — wrong in the one sentence that establishes who he is, and
  priming every answer after it. Same family as the "Samantha" voice name
  and the ⌘ key hint.
- The prompt now says he is being *listened to*, with a concrete
  before/after example rather than an abstract rule buried in a 20-line list.

**Still not fixed:** he emits a bullet list for "what can you do" no matter
how forcefully the prompt forbids it. Speech repairs it; the on-screen text
will still show bullets.

---

## 6. The wait

`"Thinking…"` was a frozen label. On a local model that takes real seconds,
a frozen label reads as a hang — the user cannot tell a model that is
working from one that has died.

`_Thinking` moves three things at three rates: the **word** rotates every
~2.8s, the **ellipsis** ticks ~2×/second, the **accent dot breathes** on a
slow sine (the same living mark the ledger already uses). Ten phrases in
Mike's register — *"Having a think"*, *"Turning it over"*, *"Piecing it
together"*. The last two (*"Getting there"*, *"Nearly there"*) are held back
for waits past ~11s, so long waits shift from novelty to reassurance instead
of cycling synonyms forever. No jokes: this appears when somebody is already
waiting, and a gag wears out on the fourth read.

Messages now fade and rise in over 180ms instead of hard-cutting into
existence as the panel jumps taller.

---

## 7. Logging was corrupting itself on every tool call

Found by an end-to-end run, not by reading code. Every *successful* tool call
wrote a `UnicodeEncodeError` traceback into the log:

```
--- Logging error ---
Message: 'Tool success: %s.%s → %s'
```

`logs/logger.py` opened its handlers with no encoding, so on Windows they
used cp1252, which cannot encode the `→` in that message — nor the em
dashes, the OAuth tick, or the microphone glyph elsewhere. The dangerous
part is that it *looks like the tool failed* when nothing did.

37 affected lines existed. Fixed the one handler instead, because chasing
characters only holds until the next em dash. `tests/test_log_encoding.py`
asserts at the handler.

---

## 8. Other real Windows bugs fixed

- **`sleep_now()` had no Windows branch** — asking Mike to sleep the PC threw
  an unhandled `NotImplementedError`.
- **`ui/instrument/tokens.py`** — `.AppleSystemUIFont`, SF Mono/Menlo and a
  hardcoded `⌘⇧space` glyph, unconditionally, on a surface visible almost
  any time the panel is hidden.
- **`tests/test_activity_finalization.py`** — a mock missing the new
  `tool_progress` signal, breaking `_retire_active_worker`.
- **Warming was per-`UIController`**, so anything building several runtimes
  queued several full 7,200-token inferences against a model that serves one
  at a time. The cache is server-side; warming twice buys nothing.

---

## 9. What was verified end-to-end

Driven through the real runtime in English, letting the model choose the
tool, then checking the machine actually changed:

```
PASS  open an app      (23s)  ['Opening Notepad']     | Notepad is now open.
PASS  open a website           browser came up
PASS  write a code file (26s)  wrote: def greet(): return "hello"
PASS  chat, no tools     (7s)  | Hey! Not much, just hanging out. How about you?
      calculate         (18s)  ['Working out 25 * 4'] | 25 times 4 is 100.
logging errors: 0
```

Plus, against the machine directly: reading the screen via UI Automation (8
live elements), and **typing into Notepad then reading the text back out via
UIA** — confirmed `True`, not a call that merely returned.

---

## 10. Disk

The machine was **completely full: 0 GB free of 202 GB** — which breaks
Ollama, temp files and installs, and is why an install test failed outright.

Reclaimed ~5.1GB, all regenerable: Gradle cache (3.96GB), Windows/user TEMP
+ pip cache + crash dumps (0.85GB), browser and VS Code caches (0.31GB),
PyInstaller intermediates and `__pycache__`.

**Deliberately kept:** 1,460MB of `faster-whisper-medium.en` — Mike's own
speech model. Wiping it would have meant a 1.5GB download the first time
anyone spoke to him.

---

## 11. Not done, unresolved, or unverified — read this part

1. **There is no shippable artifact right now.** The last rebuild was
   interrupted, and `dist/Mike-windows-1.0.0.zip` is **corrupt**
   (`BadZipFile`). A clean rebuild takes ~4 minutes. The binary in
   `dist/Mike/` is also from that interrupted build and should not be
   trusted until rebuilt.
2. **Nothing is committed.** 20 modified files, 8 new, ~990 insertions, all
   sitting in the working tree. Diff scanned, no secrets.
3. ~~**VS Code specifically is unverified.**~~ **Now verified end-to-end.**
   `is_connected: True`, `open_file -> ok`, `apply_edit -> ok`, and the file
   on disk contained the code Mike wrote. It works through the VS Code
   extension API (`vscode-extension/`, `ide/bridge.py`), not UI Automation,
   which is why Electron's UIA limitation does not apply to it.

   **The blocker was VS Code's Restricted Mode**, and it is worth writing
   down because it wastes an hour: with an untrusted folder, VS Code
   silently disables extensions. Everything looks correct -- VS Code
   running, extension installed, `code --list-extensions` listing it -- and
   nothing connects. Three separate shipping gaps came out of this:

   - the `.vsix` was never bundled in the build (`mike.spec` shipped only
     the icon), so a user who downloaded a zip had no way to get the other
     half of the protocol;
   - nothing ever installed it (`ide/install.py`, new, does this once per
     machine, finding VS Code's CLI even when it isn't on PATH);
   - the failure said "No editor is connected to Mike right now", which is
     true and useless. It now names the actual cause and the fix, leading
     with Restricted Mode.
4. **Arithmetic tool use is stochastic.** Mike called `calculate` for
   "25 × 4" but answered "47 × 12" from his head. Both answers were right;
   a wrong one would look identical. Pre-existing, documented in
   `known-limitations.md`, unfixed.
5. **A multi-file test crash is unresolved.** `test_lifecycle` passes alone
   and crashes when run alongside other files (native access violation). I
   never settled whether it is a regression of mine or a pre-existing
   threshold, because I killed the baseline comparison run to recover the
   working tree. This needs an answer before trusting CI.
6. **No installer.** Still a zip, no Start Menu shortcut, no launch-at-login
   — which the product blueprint lists as part of Windows V1 done.
7. **No wake word on Windows**, and **no scroll/drag in computer control** —
   both honest, non-crashing, pre-existing gaps.
8. **The tool schemas are ~5,400 of the ~7,200-token prefix** and are re-sent
   every turn. Affordable on the GPU; still the dominant cost on a genuinely
   CPU-only machine. Sending only relevant tools is the obvious next lever.

---

# Phase 2 — making it feel like a product

## The release is now an actual install

`Mike-windows-1.0.0.zip` (162.4 MB, 982 entries, integrity verified) now
unzips to three things, and the first is the one you double-click:

```
Install Mike.bat
install_mike.ps1
Mike/
```

Before this, "install" meant: unzip, go several folders deep, find Mike.exe,
run it from wherever it landed, and have no Start Menu entry or shortcut
afterwards. That is a developer's idea of a release.

The installer was run end-to-end from a freshly unzipped copy:

```
[1/4] Making room...
[2/4] Installing to C:\Users\...\AppData\Local\Programs\Mike
      980 files copied.
[3/4] Adding Mike to your Start Menu and Desktop
[4/4] Checking what Mike needs
      Ollama found. Mike has everything he needs.
```

Per-user by design, so it never raises a UAC prompt -- a student on a
locked-down laptop can still install it. Shortcuts verified on disk,
including the Desktop one, which correctly followed this machine's
OneDrive-redirected Desktop rather than assuming `~/Desktop`. The installed
copy launches, reports `The model is running on the GPU`, and shows the
first-run experience.

No Inno Setup or NSIS is present on this machine and adding a build
toolchain was not worth it for the gain; a PowerShell installer with a .bat
wrapper is the strongest thing available without one, and it does the job an
installer actually needs to do.

## First launch now lets you try something

`MikePanel` already had a `suggestion_clicked` signal, wired all the way
through `UIController` to `process_message` -- and nothing anywhere emitted
it. The wiring was built for a feature that was never given a face.

Four starter chips now fill it in. Every one is something verified working
on Windows, because the first thing a user asks Mike to do decides whether
they believe any of the other claims; a starter that fails is worse than no
starter. Verified on the shipped, installed build by clicking them:

```
click "Open YouTube"        -> Processing (streaming): open youtube.com
                            -> Tool success: browser.open_url -> Opened ...
click "Remember something"  -> Processing (streaming): remember that I'm
                               learning Python this term
```

## VS Code: verified, and the reason it looked broken

It works. `is_connected: True`, `open_file -> ok`, `apply_edit -> ok`, and
the file on disk held the code Mike wrote. It goes through the VS Code
extension API, not UI Automation, which is exactly why Electron's UIA
limitation does not apply.

**The blocker was Restricted Mode.** With an untrusted folder, VS Code
silently disables every extension, Mike's included. Nothing looks wrong --
VS Code running, extension installed, `code --list-extensions` listing it --
and nothing connects. Three shipping gaps came out of chasing it:

- the `.vsix` was never bundled (`mike.spec` shipped only the icon), so the
  other half of the protocol did not exist for anyone who hadn't cloned the
  repo. Now bundled.
- nothing ever installed it. `ide/install.py` now does, once per machine,
  finding VS Code's CLI even when `code` is not on PATH -- which is the
  normal case for a student who installed VS Code the normal way.
- the failure message was "No editor is connected to Mike right now",
  which is true and useless. It now names the actual cause, leading with
  Restricted Mode and how to clear it, and the README says so too.

## Coding actually works

Given a file with a real bug and told to run it, Mike ran it, read the
traceback, read the file, and said:

> "I can see the bug — on line 2, it says `len(number)` but it should be
> `len(numbers)`. Let me fix that."

Then fixed it, reran it, and got `4.0` with exit code 0. That is the whole
loop -- understand, edit, run, read the output, verify -- on a real file.

## Personality

The brief was that "I had a horrible day" should not produce a wellness
pamphlet. Measured after adding explicit guidance for emotional, stuck, and
make-me-this messages:

| said to Mike | Mike |
|---|---|
| "i had a horrible day" | *"I'm really sorry to hear that. What happened?"* (8 words, no tools, lets them lead) |
| "i'm stuck on this code and it's making me want to quit" | *"What's the problem with the code? Can you show me what you're working on?"* |
| "make me a birthday card for my friend" | calls `create_file` and makes it |

## Still true, still open

- **Barge-in by voice does not exist on Windows.** Interruption by Escape,
  the Stop button, the mic button, or simply typing is thorough and stops
  speech mid-sentence; interrupting *by speaking* needs the wake word, which
  has no Windows backend. This is a real gap in "interrupt when the user
  speaks", stated rather than papered over.
- The multi-file test crash remains unsettled (see item 5 above).
- Arithmetic tool use remains stochastic.
- Nothing is committed.
