# Mike — Professional Product & Cross-Platform Blueprint

Companion to `design/mike-product-blueprint.md` (the original 31-section
exploration) and `design/filesystem-access-proposal.md` (trust model, folded
into Phase 4 below). This document is the result of a fresh audit of the
actual repository — not the prior documents — done by tracing real imports,
the real dispatch table, and real runtime discovery logs rather than trusting
file names or comments. No implementation happened in this pass. UI/UX is
deliberately out of scope except section 11, which lists requirements without
designing anything.

**Method, briefly, because it changes what's trustworthy below:** a static
reachability trace from `main.py` found 121 files (10,558 loc) — more than
the 60 live files (8,844 loc) — structurally unreachable. Most of `ui/`
(caret/, home/, most of widgets/) is genuinely dead: earlier rejected visual
directions left on disk. Almost all of `tools/` looked unreachable by the
same static trace but isn't — `brain/core_tools.py` discovers `tools/`
subpackages dynamically at startup (confirmed against the real init log:
"Discovering package: tools.email" → "Registered capability: email"), so
static import-following misses it. Every finding below was cross-checked
against that discovery log and the actual `DISPATCH` table, not the static
trace alone — the trace found the candidates, the dispatch table decided
what's real.

---

## 1. Complete product capability map

Legend: **BUILT+READY** · **BUILT+POLISH** (works, rough edges) ·
**PARTIAL** · **INFRA-ONLY** (plumbing exists, not reachable by the model or
the user) · **DESIGN-ONLY** · **MISSING** · **DEFERRED** (built, cut from
this pass on purpose) · **BLOCKED** (needs a decision first).

### Core AI

| Capability | Status | Evidence |
|---|---|---|
| Conversation (streaming, tool calls, Agency V1 multi-step) | **BUILT+READY** | `brain/core_runtime.py` `_streaming_loop`, verified this session |
| Context / situation awareness | **BUILT+READY** | `mike_core.to_prompt_context()` |
| Memory (durable, categorized) | **BUILT+READY** | `memory_store.py`, Memory UI built + hardened this session |
| Project continuity | **BUILT+READY** | `projects.py` + `sync_project()`, built + hardened this session |
| Model management / switching | **MISSING** | One model hardcoded per role (`qwen3:8b` chat, a summary model). No UI, no config surface, no fallback model |
| Context limits | **BUILT+POLISH** | `MAX_HISTORY=40` turns, hard-trimmed with a background situation-summary as the only compression. No token-aware trimming |
| Streaming | **BUILT+READY** | Real token-by-token, verified |
| Cancellation | **BUILT+READY** | Verified end-to-end this session, one real race found and fixed |
| Retries | **MISSING** | Zero retry/backoff anywhere in the Ollama call path — grepped, confirmed absent. A transient failure surfaces immediately as a (well-humanized) error |
| Offline / degraded behavior | **BUILT+POLISH** | `brain/diagnostics.check_ollama()` (built this session) distinguishes "not reachable" / "reachable, model missing" / "was fine, one-off" — but only for the *local* model. No behavior at all if the network is down (irrelevant, local-first) or if a *tool* dependency (e.g. Gmail token) is broken — that surfaces as a raw exception |
| Conversation persistence | **MISSING** | `MikeCore.history` is an in-memory Python list only. Only the *compressed situation summary* survives restart (`situation_store`) — the raw transcript does not |
| Conversation search | **MISSING** | Nothing to search — no transcript is stored |
| Conversation export/delete | **MISSING** | Same root cause |

### Computer agency

| Capability | Status | Evidence |
|---|---|---|
| Filesystem (read/write/create/delete/move/copy/rename/list/open) | **BUILT+READY** | `tools/filesystem/actions.py`, in live `DISPATCH` |
| Filesystem permissions/scoping | **DESIGN-ONLY** | `design/filesystem-access-proposal.md` (this session) — confirmed *zero* path scoping exists; only action-type confirmation |
| Terminal (`run_command`, `run_background`) | **BUILT+POLISH** | Live, confirmed timeout + confirmation gate. `run_background` spawns via `Popen` with no list/kill/monitor surface — a background process, once started, is invisible to Mike and the user afterward |
| Applications (`open_application`) | **BUILT+READY** | Live |
| Browser (`open_browser`, `open_url`, `search_web`) | **BUILT+READY** | Live |
| IDE (context, open file, apply edit) | **BUILT+READY** | `ide/` package + real VS Code extension (`vscode-extension/`, packaged `.vsix`, v0.1.0) — genuinely working, not a stub |
| Processes (list/kill/inspect beyond spawn) | **MISSING** | No structured process management; only escape hatch is asking the model to run `kill` via `run_command` |
| System state (lock/sleep/restart/shutdown) | **BUILT+POLISH** | Registered live (`tools/system`), but not in the model-facing `DISPATCH` table at all — same infra-only pattern as email (below). Confirm before trusting the label "built": it's *discoverable*, not *callable* |
| Clipboard | **MISSING** | Zero references anywhere in `tools/`/`brain/` |
| Notifications (OS-level) | **MISSING** | Zero references. Mike has no way to reach the user when the app isn't focused, beyond the Edge strip (which requires the app to still be running — see §5) |
| Screenshots / vision | **BUILT+READY** | `vision/screenshot.py` (`screencapture`) + `see_screen` tool, freshness-windowed in `mike_core._fresh_vision` |
| Multi-step actions (Agency V1) | **BUILT+READY** | Verified |
| Cancellation | **BUILT+READY** | Verified, one real bug fixed this session |
| Recovery / undo | **BUILT+READY** | Revert-by-snapshot, built + hardened this session (was missing its own safety net until this pass) |
| Action history | **BUILT+READY** | `activity_store.py`, Activity tab |
| Confirmation gate | **BUILT+READY** | Single, non-duplicated gate (`_CONFIRM_ACTIONS`) |
| Destructive operations | **BUILT+POLISH** | Gated by confirmation + now-safety-netted by revert; still no scoping (see filesystem permissions above) |

### Communication

| Capability | Status | Evidence |
|---|---|---|
| Voice input | **BUILT+READY** | Adaptive-threshold recorder (recent uncommitted work — see §Notes below) |
| Voice output (TTS) | **BUILT+READY** | macOS `say`, streamed sentence-by-sentence |
| Interruption (barge-in) | **BUILT+READY** | Built + verified this session |
| Wake word | **BUILT+READY**, macOS-only | `AppKit.NSSpeechRecognizer` via PyObjC — real native speech recognition, not a stub, but architecturally the single hardest thing to port (§4) |
| Global invocation (hotkey) | **BUILT+READY**, macOS-only | Carbon `RegisterEventHotKey` via raw `ctypes` |
| Keyboard shortcuts | **BUILT+POLISH** | F6 (voice), Ctrl+L (clear), Escape (cancel/close-overlay) — real, but that's the entire set; no shortcut for switching rooms, no discoverability (no shortcut list anywhere in the UI) |
| Accessibility | **MISSING** | Every interactive control in the Instrument UI (room tabs, forget, revert, settings toggles) is a bare `QLabel` with a mouse handler — no keyboard focus, no tab order, no screen-reader semantics, anywhere |
| Notifications | **MISSING** | Same as above |
| Background presence | **BUILT+POLISH, with a real inconsistency** | Minimizing keeps Mike alive with the Edge strip ambient (`hideEvent`→`edge.wake()`). But `ui/app.py` never calls `setQuitOnLastWindowClosed(False)` and there's no system-tray icon — **closing the main window's × button fully quits the app**, unregistering the global hotkey and killing the IDE bridge. This directly contradicts what Mike tells the user in his own onboarding text: *"I stay running in the background... nothing about this ever leaves this machine."* A user who closes the window the way they'd close any other app has, without being told, turned Mike off entirely. |

### Memory / context

| Capability | Status | Evidence |
|---|---|---|
| Durable memory | **BUILT+READY** | (see Core AI) |
| Project memory | **BUILT+READY** | |
| Global memory | **BUILT+READY** | |
| Situation summaries | **BUILT+READY** | Restart-persistent, project-scoped |
| Activity | **BUILT+READY** | |
| Conversation history (raw) | **MISSING** | (see Core AI) |
| Generated artifacts (tracked as a first-class thing) | **MISSING** | A file Mike creates is only visible as an Activity row + optional revert snapshot — there's no "things Mike made" view |
| Project relationships | **MISSING** | `projects` is a flat table (path → name → last-active). No hierarchy, no "this project relates to that one" |
| Deletion | **PARTIAL** | Memory: yes (per-row "forget", built this session). Activity/revert history: no delete at all. Conversation: moot, nothing persists |
| Export / import | **MISSING** | No export of memory, activity, or preferences in any form |
| Backup / recovery | **MISSING** | Single SQLite file, no backup, no "restore from before" beyond the per-file revert mechanism |

### Product

| Capability | Status | Evidence |
|---|---|---|
| Onboarding | **BUILT+READY** | Built this session, one-time intro, gated correctly |
| Settings | **BUILT+POLISH** | 2 real toggles (voice, wake word) + read-only status rows. Functional, thin |
| Personalization | **MISSING** | Beyond the 2 toggles, nothing — no name, no tone, no working hours, no anything |
| Privacy | **BUILT+POLISH** | Real (zero network calls verified this session and last), but *stated*, not *enforced or inspectable* — no "show me what's stored" beyond the Memory tab specifically |
| Permissions | **DESIGN-ONLY** | (see filesystem-access-proposal.md) |
| Diagnostics | **BUILT+POLISH** | `brain/diagnostics.py`, Ollama-only, built this session |
| Updates | **MISSING** | No updater, no version-check, no update channel of any kind |
| Versioning | **INFRA-ONLY** | `config/settings.VERSION = "1.0"` exists but is *never read anywhere* — not shown in the UI, not logged, not compared against anything |
| Crash recovery | **MISSING** | No crash handler, no "recover unsent draft," no restart-after-crash state beyond what SQLite/situation persistence gives incidentally |
| Logs | **BUILT+POLISH, one real gap** | `logs/logger.py` writes to a *relative* `logs/mike.log` path — depends on the process's cwd at launch, which breaks the moment this becomes a packaged `.app` launched from Finder/Spotlight rather than a terminal. No rotation, no size cap, no in-app "view logs" |
| Telemetry / privacy model | **BUILT+READY (by omission)** | No telemetry exists. This is a real, positive, deliberate property — worth stating as a *feature*, not a gap |
| Account / authentication | **N/A by design**, except email | Local-first, no Mike account. The one exception is Gmail OAuth (`auth/`, `credentials.json`) for the email tool — see below, it's currently unreachable anyway |
| Data migration | **BUILT+POLISH** | The `PRAGMA table_info` + `ALTER TABLE` guard pattern built this session is the only precedent; untested at a second migration |
| Reset / uninstall | **MISSING** | Zero "clear all my data" flow. A user who wants to start over must manually find and delete `~/Library/Application Support/Mike/` themselves, unguided |
| Accessibility | **MISSING** | (see Communication) |
| Localization | **MISSING** | English-only, strings hardcoded throughout; no i18n scaffolding anywhere |
| Keyboard navigation | **MISSING** | (see Communication) |

### Integrations

| Capability | Status | Evidence |
|---|---|---|
| IDEs (VS Code) | **BUILT+READY** | Real bridge, real packaged extension |
| Email | **INFRA-ONLY — this is the sharpest "no vaporware" finding in this audit** | `tools/email/` is a complete, real Gmail OAuth client (`gmail_client.py`, `oauth.py`, real send/read logic) and it *is* dynamically discovered and registered as a capability at startup ("Registered capability: email" in the real init log). But **`brain/core_tools.py`'s live `DISPATCH` table — the only thing the model can actually call — has zero email-related entries.** Grepped directly, confirmed absent. The model cannot send or read email today, at all, despite the plumbing existing and "registering" successfully. This is exactly the built-infrastructure-vs-working-feature gap the audit was told to watch for |
| Browser | **BUILT+READY** | |
| Developer tools | **BUILT+READY** | via IDE bridge |
| Filesystem | **BUILT+READY** | |
| OS services (system tool) | **INFRA-ONLY** | Same pattern as email — registered, not dispatched |
| Third-party integrations | **MISSING** | None, no extension point for one either |

---

## 2. What a professional Mike must have

Answering the user's own framing directly — *"if someone installed Mike
tomorrow and used him as their primary desktop AI assistant, what would they
reasonably expect to work?"* — against the map above, in the order a real
user would hit them:

- **Background presence that means what it says.** The onboarding text
  promises "I stay running in the background." Today, closing the window
  breaks that promise silently. This is the single most damaging gap in the
  map — not because it's hard to fix, but because it makes Mike's own stated
  identity false the first time someone does the single most natural thing
  (click the red button).
- **A finished feature over a discovered one.** Email is fully built and
  completely unreachable. A professional product doesn't ship a capability
  that quietly does nothing — either wire it in or don't claim it.
- **Conversation continuity a user can trust past a restart.** Situation
  summaries are real continuity, but they're a compression, not a record. A
  user who says "what did I ask you yesterday" gets nothing, because nothing
  is kept.
- **A way to leave.** No reset, no export, no uninstall path. A professional
  product that asks for this much filesystem/terminal/browser trust needs an
  equally clear way to undo that trust completely, not just per-memory
  "forget."
- **Recovering from its own failures gracefully.** No retries on a flaky
  local model call is a small thing that will be felt constantly — Ollama
  hiccups are common, not exceptional.
- **A first-class place to see and reach what Mike already registered.**
  System actions (lock/sleep/shutdown) are built and registered exactly like
  email — also unreachable. Whatever the plan for email turns out to be, the
  same decision applies here.

## 3. What we are currently missing

Consolidating the map's **MISSING** rows into one list, because several of
them are more foundational than they look in isolation:

1. Conversation persistence, search, export, delete (all one root cause)
2. Filesystem permission/scoping (proposed, not built)
3. Reset / uninstall / "start over" flow
4. Retry/backoff on model calls
5. Clipboard access
6. OS notifications
7. Structured process management (list/kill what Mike started)
8. Accessibility (keyboard nav, focus, screen-reader semantics) — universal, not feature-specific
9. Updates / version awareness
10. Crash recovery
11. Backup/export of Mike's own state
12. True background presence (system tray or equivalent, see §1)
13. Personalization beyond two toggles
14. Localization readiness (not localization itself — the scaffolding)

None of these are surprising individually. What's worth naming: **#2, #12,
and #8 are the three that change architecture, not just add a screen** — the
rest are additive.

## 4. Cross-platform architecture

### The real macOS-specific surface — precisely, not by guess

A targeted trace (not a guess at "probably platform code") found exactly
**five modules with real OS-native dependencies**, plus one path convention
repeated six times:

| Module | macOS mechanism | Depth |
|---|---|---|
| `ui/system/global_hotkey.py` | Carbon `RegisterEventHotKey` via raw `ctypes` | Deep — low-level OS API, no Python wrapper in between |
| `voice/wake_word.py` | `AppKit.NSSpeechRecognizer` via PyObjC (`pyobjc-framework-Speech`/`-Cocoa`) | Deep — native Cocoa binding, not a CLI shell-out |
| `voice/speaker.py` | `say` CLI via `subprocess` | Shallow — a shell-out, easy to swap |
| `vision/screenshot.py` | `screencapture` CLI via `subprocess` | Shallow — and a cross-platform library (`mss`, or `PIL.ImageGrab`) could replace it *on both platforms*, not just add a Windows branch |
| `brain/environment.py` | `osascript` → System Events, for frontmost-app name | Shallow — shell-out, easy to swap |
| *(repeated 6×, not one module)* | `Path.home() / "Library" / "Application Support" / "Mike"` hardcoded identically in every store | Trivial — one shared helper fixes all six at once |

Two things follow directly from this shape. First, it's a **much smaller
surface than the size of the repo suggests** — five files and one repeated
path pattern, not a pervasive assumption. Second, it's **uneven**: three of
the five (`speaker`, `screenshot`, `environment`) are thin shell-outs a
Windows adapter can replace in an afternoon each; two (`global_hotkey`,
`wake_word`) are genuine native-API integrations that need real Windows-side
engineering, not just a different subprocess call.

The IDE bridge (`ide/manager.py` and everything under `ide/`) is already
clean — pure sockets, zero OS-specific code, confirmed by direct import
trace. It needs nothing for Windows.

### The boundary

```
CORE (platform-independent — the great majority of the repo)
│
├── brain/          — MikeCore, CoreRuntime, all stores, core_tools DISPATCH
├── ide/             — bridge, contracts, VS Code adapter (already portable)
├── tools/           — filesystem, terminal, browser, email, system actions
├── ui/instrument/    — the live Qt surfaces (Qt itself is cross-platform)
├── ui/controller/    — UIController, worker threads
└── config/          — preferences, settings

PLATFORM ADAPTERS (one small interface per real divergence, nothing more)
│
├── GlobalHotkey        .register(callback) / .unregister()
│     macOS: ui/system/global_hotkey.py (Carbon, unchanged)
│     Windows: RegisterHotKey via ctypes (Win32 API) — same shape of solution,
│              new implementation
│
├── SpeechSynthesizer    .speak(text) / .stop()
│     macOS: say subprocess (unchanged)
│     Windows: SAPI via pywin32 or pyttsx3
│
├── WakeWordDetector     .start() / .stop() / on_wake callback
│     macOS: NSSpeechRecognizer (unchanged)
│     Windows: needs its own decision — see below, this is not a
│              like-for-like port
│
├── Screenshotter        .capture() -> Path
│     Both platforms: recommend replacing the macOS-only screencapture
│     shell-out with mss or PIL.ImageGrab — a single cross-platform
│     implementation, not two adapters. This removes one adapter entirely.
│
├── ActiveWindowDetector .current() -> str | None
│     macOS: osascript (unchanged)
│     Windows: win32gui.GetForegroundWindow + win32process
│
└── AppDataDir            a five-line function, not really an "adapter"
      macOS:   ~/Library/Application Support/Mike
      Windows: %LOCALAPPDATA%\Mike
      Used by all 6 stores instead of each hardcoding the macOS path.
```

Deliberately **not** introducing a boundary for anything else — filesystem
actions, terminal execution, browser control, and the Qt UI itself are
already cross-platform (Python `pathlib`/`subprocess`/PySide6 work
identically on both OSes with no adapter needed). Over-abstracting those
would be exactly the "sprinkle platform checks everywhere" the brief said
not to do.

### The one decision this surfaces: wake word

Porting `NSSpeechRecognizer` 1:1 isn't really possible — it's Apple's
on-device recognizer, there's no Windows equivalent with the same
characteristics. Two real options, not a foregone conclusion:

- **A: Windows-native equivalent** — Windows Speech Recognition via
  `System.Speech.Recognition` (through `pywin32`/`.NET` interop). Keeps each
  platform on its OS's own best recognizer, at the cost of two genuinely
  different implementations to maintain.
- **B: One shared, cross-platform wake-word engine for both OSes** (e.g.
  openWakeWord, or a small local model) — replaces the macOS implementation
  too, so wake-word behavior is identical on both platforms and there's one
  implementation instead of two. Costs giving up the free, high-quality,
  zero-dependency native recognizer macOS already has.

This needs a real decision before Windows wake-word work starts — it isn't
a mechanical port like the other four adapters.

### Packaging — currently absent on both platforms

No `.spec`, `setup.py`, `pyproject.toml`, or bundle config exists anywhere in
the repo. Today, Mike runs by invoking `python main.py` directly. There is
also no launch-at-login mechanism (no LaunchAgent plist, nothing). Both are
real, unstarted work — not a platform-adapter problem, a packaging-pipeline
problem, needed once per platform (PyInstaller/py2app + a `.app` bundle and
LaunchAgent for macOS; PyInstaller + an installer, likely NSIS or MSIX, and
a startup registry entry for Windows). `requirements.txt` currently mixes
macOS-only wheels (`pyobjc-*`) with universal ones and includes real dead
weight (`customtkinter`, `darkdetect` — no import anywhere in the live or
even the dead-but-present code; `groq`, `openai` — unused client libraries
matching the already-confirmed-dead API keys in `.env.example`) — a
per-platform requirements split is needed regardless of the adapter work,
and it's a good moment to drop the unused packages rather than carry them
into two platform-specific builds.

---

## 5. Trust / safety model

Extending `design/filesystem-access-proposal.md` (folder-level filesystem
scope, additive to the existing action-type confirm gate) across every
surface the audit above touched, using the same six questions:

| Surface | What Mike can know/see | What requires confirmation (today) | What should require a standing grant |
|---|---|---|---|
| Filesystem | Read anywhere (unchanged) | Write/delete (existing gate) | **New**: write/delete *outside* default+project scope — the filesystem proposal |
| Terminal | N/A | `run_command`/`run_background` (existing gate) | Nothing new — a command is a command, scoping it by *directory* would be the filesystem grant applied to `cwd`, not a separate model |
| Browser | N/A | Nothing today (`open_url`/`search_web` are unconfirmed) | Nothing new — browsing isn't destructive and doesn't touch local state |
| IDE | Whatever workspace is connected (opt-in per-project via the VS Code extension's own `mike.enabled` toggle) | `ide_apply_edit` (existing gate) | Nothing new — the extension's own enable/disable is already the standing grant, per project, and it already works |
| Email | Nothing today — unreachable | N/A (not dispatched) | **Blocked on a decision, not built yet**: if/when wired in, `send_email` is unambiguously a `_CONFIRM_ACTIONS`-class action (irreversible, external, visible to a third party) — no new model needed, it slots into the existing gate exactly like `write_file` does |
| Unattended/scheduled actions | — | — | **The one genuinely new category.** Nothing today has any notion of "act without a human present to confirm." Any scheduling feature needs its own answer to "what may happen with nobody watching" *before* it exists — most plausibly, a scheduled action is only ever allowed to touch what's already been granted standing access to (filesystem scope, once built), and anything that would normally require a one-off confirm simply doesn't run unattended at all rather than silently auto-approving |
| System actions (lock/sleep/shutdown) | — | Currently unreachable (infra-only) | If wired in: confirmation, same as today's gate — these are visible/disruptive but not data-destructive, arguably lighter-weight than a file delete |
| Application control | — | Unconfirmed today (`open_application`) | Stays unconfirmed — opening an app is not destructive |

**Where Mike can do it** is exactly the filesystem-scope proposal (folder
grants, listed and revocable in Settings). **When** is the new question this
pass surfaces, and it only matters once scheduling exists — there's no need
to solve it before that, only to make sure scheduling doesn't get designed
without an answer to it.

**How the user understands all of this**, kept to what's already proven to
work this session: one settings section ("Where Mike can act") lists every
standing grant — folders, and later, IDE connections and any scheduled
actions — in the same plain list-with-an-undo-link language as the Memory
tab already uses. No permission matrix, no tiers, no separate "trust center"
screen.

## 6. Remaining product decisions

Ranked by how much they block other things, not by how interesting they are:

1. **Filesystem access scope** — proposed, not built. Blocks scheduling
   (§5), blocks any confident answer to "where can Mike act" in general.
2. **Background presence model** — tray icon vs. current window-close
   behavior. Blocks nothing else technically, but is a trust/honesty issue
   *today*, independent of any new feature — Mike currently claims
   something about himself that isn't true the moment the window closes.
3. **What to do with infra-only capabilities (email, system actions)** —
   either wire them into `DISPATCH` behind the filesystem-style confirm gate,
   or stop registering them as capabilities until they are. Leaving them
   half-built as-is is the one state that's actively worse than either
   choice, because "Registered capability: email" in the logs currently
   describes a capability that does not exist from the model's point of
   view.
4. **Conversation persistence model** — a full transcript store, or a
   richer situation-summary (multiple summaries, longer retention), or both.
   Affects search/export/delete, which are currently impossible by
   construction, not by omission.
5. **Wake-word strategy for Windows** (§4) — native-per-platform vs. one
   shared engine. Only blocks Windows wake-word work specifically.
6. **Packaging/distribution approach** — PyInstaller vs. py2app/briefcase,
   code-signing and notarization strategy for macOS, installer format for
   Windows. Blocks nothing else, but has real lead time and should start
   before it's the last thing standing between "done" and "shippable."

## 7. Prioritized implementation roadmap

Grouped by the user's own A–E scale, with dependencies called out inline.

**A — must-have before calling Mike a serious product**
- Fix background-presence honesty: either add a real tray/menu-bar presence
  and make closing the window hide rather than quit, or change the
  onboarding claim to match reality. (Independent, no dependency, should be
  first — it's a correctness fix, not a feature.)
- Resolve and build filesystem access scope (§5/§6-1). Blocks scheduling and
  is the actual foundation the rest of "trust" sits on.
- Decide and act on email + system-actions: wire in behind the confirm gate,
  or stop advertising them as registered capabilities. (Depends on the
  filesystem-scope decision only if email's target paths — attachments —
  need scoping too; sending itself doesn't.)
- A real reset/uninstall path — at minimum, a Settings action that clears
  the SQLite store and preferences file with the same plain confirm
  language as everything else.
- Retry/backoff on the model call path — small, high day-to-day value.
- AppDataDir helper (§4) — five lines, unblocks nothing by itself but is a
  prerequisite for any Windows work and costs almost nothing to do now.

**B — important polish**
- Conversation persistence (transcript store) + search + export/delete.
  Depends on nothing technical, but is a real design decision (§6-4) worth
  making deliberately rather than bolting on.
- Accessibility pass on the existing Instrument controls (keyboard focus,
  tab order) — worth doing before the eventual redesign, not after, so the
  new design inherits real keyboard semantics instead of reintroducing the
  same gap.
- Structured process management for `run_background` (list/kill what Mike
  started).
- Fix the relative `logs/mike.log` path before packaging makes it worse.
- Clipboard access (low effort, real day-to-day value for a "lives on your
  computer" assistant).

**C — valuable, can follow launch**
- OS notifications.
- Personalization beyond the two existing toggles.
- Backup/export of Mike's own state as a whole (not per-feature).
- Model management/switching (multiple local models, a way to pick).
- Windows platform adapters + packaging (§4) — large, real, but additive
  once the core decisions in A are settled. Doing this before A would mean
  building two platforms on top of an access model and a background-presence
  story that are both still wrong.

**D — future / experimental**
- Multi-device or any notion of Mike's state syncing anywhere (in real
  tension with the local-first premise — worth treating as "maybe never,"
  not just "later").
- Third-party integration framework beyond IDE/email.
- Localization.

**E — explicitly not worth building**
- A general-purpose permission-matrix/tiers UI — the filesystem proposal and
  §5 both deliberately reject this shape; adding it later would undo that.
- Rebuilding or reviving `tools/permissions/`, `memory/`, or
  `core/tool_executor.py`/`services/` — three separate dead parallel
  architectures already found in this repo (this session and the last).
  Delete-on-sight candidates, not refactor candidates.
- A cloud/account layer for its own sake — nothing in the audit found a real
  need for one; local-first is a stated identity, not just a current
  limitation.

## 8. macOS V1 — definition of done

- Every **A**-tier item above, on macOS.
- Background presence actually matches what onboarding says.
- Filesystem scope built and surfaced in Settings.
- Email and system actions are either real (wired + confirmed) or no longer
  claimed as registered capabilities.
- Packaged as a signed, notarized `.app` with a LaunchAgent for
  launch-at-login — not run from a terminal.
- `logs/mike.log` resolves to a real app-data path regardless of launch
  method.
- The five existing hardened features (Memory UI, onboarding, project
  continuity, barge-in, revert) remain exactly as verified this session —
  this pass adds to that baseline, it doesn't touch it.

## 9. Windows V1 — definition of done

- Everything in macOS V1's definition, on Windows, via the adapters in §4.
- Wake-word strategy (§6-5) decided and implemented — not deferred silently.
- Global hotkey working via the Win32 adapter, with the same "reachable the
  moment the app launches" property the Carbon implementation has today
  (worth checking whether the Win32 equivalent needs any permission prompt
  the Carbon route currently avoids).
- TTS via SAPI, screenshot via a cross-platform library (ideally shared with
  macOS, per §4), frontmost-window via `pywin32`.
- Installer (NSIS or MSIX) + startup registry entry for launch-at-login.
- `pyobjc-*` dependencies excluded from the Windows requirements split;
  confirmed the app installs clean without them.
- Not required for V1: feature parity on anything already marked
  INFRA-ONLY/MISSING on macOS — Windows V1 matches macOS V1, not some
  larger future scope.

## 10. Features to deliberately not build

- A permission-tiers/matrix UI (§7-E).
- Reviving any of the three dead parallel architectures already found
  (`memory/`, `tools/permissions/` + `core/tool_executor.py` +
  `services/`, and whatever `ui/home/`+`ui/caret/` were building toward —
  120+ files of prior, abandoned direction already on disk).
- A cloud account/sync layer.
- Multi-model orchestration/agent marketplace-style extensibility — nothing
  in the current product or the audit points to a real need for it, and it's
  exactly the kind of complexity that sounds impressive without serving a
  concrete user need.
- Telemetry, in any form — the current zero-telemetry stance is a real
  asset, not a placeholder waiting to be filled in.

## 11. Eventual UI/UX requirements (no redesign)

Not a design — a list of what the *information* the future UI has to carry,
so the redesign inherits real requirements instead of just what
Home/History/Settings happened to grow.

**States that must be representable** (superset of today's
idle/listening/thinking/working/needs_user/responding/error):
add "unattended action pending" (once scheduling exists) and "capability
unreachable" (for the infra-only case, if that's how it's ultimately
resolved rather than removed).

**Surfaces that must exist**, regardless of navigation shape:
- A conversation surface (today: Chat) — will need to represent *found*
  results if search ships (§7-B).
- A record of what Mike did (today: Activity) — already handles revert;
  will need to represent process-management (start/list/kill) if that ships.
- A record of what Mike knows (today: Memory) — already handles per-item
  forget.
- A place for standing grants (today: nothing; proposed in §5/§6) — folders,
  and eventually any scheduled/unattended permissions — needs the same
  plain list-with-undo language the Memory tab already proved works.
- A settings surface — will grow from 2 toggles to real personalization
  (§7-C) and needs room for that without becoming a preferences dump.
- A background/ambient presence (today: Edge strip) — needs to keep working
  once real background presence (§6-2) exists, likely becoming the primary
  "Mike is here but idle" surface rather than a fallback.

**Ambient vs. explicit**, the distinction already implicit in today's
Edge/Invoke/Home depth ladder and worth carrying forward as a *requirement*
even if the visual language changes: presence, "something needs you," and
"something finished" should stay ambient; anything that reads *content*
(a memory, an activity detail, a settings change) should require deliberate
entry into a fuller surface. Whatever the new IA is, it should preserve that
split.

**Must work identically on Windows**: everything above — no
platform-specific surface, only platform-specific *plumbing* underneath
(§4). The redesign should assume Windows exists from the start rather than
retrofitting it.

**Accessibility must be load-bearing this time**, not retrofitted: keyboard
focus, tab order, and screen-reader semantics for every interactive element
are a *requirement* of the next UI, not a follow-up pass — the current
Instrument UI's uniform lack of them (§1, §3) is the mistake not to repeat.

## 12. Strongest recommendation

Fix the background-presence honesty gap first, before anything else in this
document, including the filesystem access model. It's the smallest possible
change (a tray icon or equivalent, plus intercepting the close event) and it
fixes something that's actively false *right now*, every time a real user
does the single most ordinary thing — closes the window. Everything else in
this blueprint is about building forward; this one is about a claim Mike
already makes about himself that the code doesn't keep. Ship that fix,
*then* take on filesystem scope as the true first major build — in that
order, not the reverse, because the trust model in §5 assumes Mike is
actually still running when it says it is.

---

*No code was written for this document. `design/mike-professional-product-blueprint.md` is the reference to work against feature-by-feature, per the instruction that opened this phase.*
