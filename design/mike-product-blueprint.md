# Mike — Master Product Blueprint

*Grounded in the actual repository as it stands today — not in prior design docs, and not in what other AI products do. Every capability claim below was verified against real code before being written down. Where I'm proposing something new, I say so.*

---

## 1. Product thesis

**Mike is the machine's attention, not an app on it.**

Three things are true about Mike that are not true of any well-known competitor, and they are true *today*, in working code, not as marketing:

1. **Nothing leaves the machine.** Verified: `OLLAMA_MODEL = "qwen3:8b"` is hardcoded in `core_runtime.py`; the cloud keys sitting in `.env` (`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`) are read by `config/settings.py` and used by nothing else in the live path. This isn't a toggle that could regress — there's no code path that would send a message off the Mac.
2. **He acts, not just talks.** 21 real tool declarations in `brain/core_tools.py` — filesystem, terminal, browser, an editor bridge, screen vision, memory. A single `_CONFIRM_ACTIONS` frozenset gates every action that writes, deletes, or executes.
3. **He has continuity infrastructure most local AI tools don't bother with.** `brain/situation_store.py` persists a standing summary of "what's going on" to SQLite and reloads it on every launch — Mike remembers the shape of what you were doing before he was closed, not just facts you told him to remember.

The thesis: **a local-first computer operator with real hands and honest memory, reachable the instant you need him and invisible the instant you don't.** Not a chatbot. Not a voice assistant. Not an agent-framework demo. The product bet is that *presence* + *trust* + *actually doing things* beats *more capability behind a bigger chat window*.

---

## 2. Who Mike is

Think "a sharp junior engineer who sits at your machine, not a genie and not a friend." He:
- knows what app you're in and what's on screen when it matters, without narrating it back at you
- remembers a short list of durable facts about you and your work, and will say exactly why he believes each one
- will read a file, run a command, open a browser, or edit code — after telling you what he's about to do, for anything destructive
- doesn't pretend to know things he doesn't, doesn't invent progress he hasn't made, and says "I don't know" or "I can't tell how many steps this'll take" when that's the truth

He is not warm in the "companion app" sense and not cold in the "enterprise tool" sense. The register is competent and direct — closer to a good colleague than to Siri or to a customer-support bot.

---

## 3. Core user relationship

The operating relationship is **owner and operator, not user and product.** The user owns the machine; Mike operates on it *with permission*, every time, for anything that can't be undone. This isn't a policy bolted on top — it's the actual shape of the safety gate already in the code (`_CONFIRM_ACTIONS`), and it should stay the organizing metaphor for everything else: settings, memory, projects. The user is never "using an app's features" — they're directing an operator who happens to live in software.

Two consequences worth stating plainly:
- **Mike defers.** He never has standing authority to do something destructive twice in a row without being asked again — no "always allow" checkbox anywhere in this blueprint. If that changes, it should be a deliberate, visible decision (see §20).
- **Mike is legible.** Everything he remembers, everything he's done, is something the user can open and read in plain language — not logs, not JSON. This is the throughline for §11, §14, and §19.

---

## 4. Interaction model

The existing depth ladder — ambient / edge / invocation / dwelling / embedded — has survived three complete visual rewrites (orb → caret → instrument) essentially unchanged. That's real evidence it's the right skeleton; what kept breaking was the visual language sitting on top of it, not the ladder itself. **Keep it, rename two rungs for clarity, tighten the escalation rule.**

| Depth | What it is | When |
|---|---|---|
| **Present** (was D0) | Running, listening for the wake word, holding situation. Zero pixels. | Always, by default. |
| **Glance** (was D1) | A small opening at the screen edge — a fact, a running action, a question. Never takes focus. | Something worth a half-second of attention exists. |
| **Summon** (was D2) | A single line, deliberately invoked, that can take focus because you asked for it. | You pressed the key, or said the word. |
| **Dwell** (was D3) | The full window — conversation, activity, memory, settings. | You want to spend real time: read back, correct something, configure. |
| **Embedded** (D4) | Inside another app — currently the editor bridge, invisibly. A future visible presence here is a real possibility, not yet product. | While working inside a connected tool. |

**The one rule that matters more than the ladder itself:** Mike may go *deeper* only on explicit user action. He may never self-promote from Glance to Summon, or from Summon to Dwell. A two-second question gets a Glance-depth answer and nothing else opens. A long project never gets squeezed into a Summon-depth line — it should *offer* to open Dwell, never force it. This rule already holds in the current build (`InvokeLine` never opens `HomeSurface` on its own) and should hold for everything built on top of it.

---

## 5. Information architecture

The live product currently has three rooms: Chat, History, Settings. That's not a placeholder — it's close to correct, and the reason it's correct is worth stating: **a real user doesn't think in the categories a design document invents ("Record," "Conduct," "Mind"). They think in three questions**:

1. *What's happening / let me talk to Mike* → the default surface, not a "room" at all
2. *What has Mike done, and what does he know* → one room
3. *How does Mike behave, and what can he touch* → one room

That third question was already validated directly by the user rejecting "Record" and "Conduct" as unclear and accepting "History" and "Settings" as obvious. I'm not re-litigating that.

**What I am changing:** question 2 should absorb memory when memory gets a UI (§11), rather than spawning a fourth top-level room. "What has Mike done" and "what does Mike know" are the same *kind* of question — both are "let me look back" — so History becomes a room with two tabs (Activity / Memory) rather than two separate destinations. Projects (§13) should **not** be a fourth top-level room either — it's a *scope* you enter from Chat, not a new place you go.

**Final IA:**

```
Chat            (default — this is Mike, not a "room")
History         → Activity tab (built)  |  Memory tab (design only, §11)
Settings        → Behaviour | Reach | Privacy  (built, minus real permissions UI)
```

Three destinations. Not four, not seven. Everything else — Projects, Library, Schedules — is either a *mode* of Chat (Projects) or doesn't earn a place in the IA yet because there's no substrate (Library, Schedules — see §15, §16).

---

## 6. Main product surfaces

Covered in depth in §4–§5. The one surface not yet named: **the composer itself is one object across every depth** — same dial, same line, same "type or just talk" affordance at Glance, Summon, and Dwell. That consistency (already true in the current build — `Composer`, `InvokeLine`, and the edge strip all embed the same `Dial` class) is a real asset and should be a hard constraint on any future redesign: there is one way to talk to Mike, rendered at different sizes, never three different input patterns.

---

## 7. Computer-native behaviour

Verified real signal sources today: frontmost application (`brain/environment.py`), IDE context when VS Code is attached (`ide/manager.py` — file, workspace, selection, diagnostics), a single-shot screen description on request (`vision/vision.py`, tool-invoked, not continuous). Not present: clipboard, running-process list, notification access, browser tab/URL awareness outside what's manually described, window enumeration.

**Product decision: most of this stays invisible infrastructure, not a feature.** The user should never manage "what Mike can see" as a settings screen full of toggles for clipboard/processes/windows. Two exceptions earn a real UI:

- **Where Mike is right now** — already surfaced as the context label in Home's rail and top bar. Keep it; it's the single most important piece of computer-native honesty in the product, because it's the answer to "does Mike actually know what I'm looking at."
- **What Mike can reach** — IDE bridge status, already in Settings. This is a *reach* question (§20), not a *behaviour* question, and belongs there.

Everything else (clipboard, processes, notifications) is **future substrate, not future product** — build the plumbing quietly when a real use case demands it (e.g., "paste what I copied" needs clipboard access), expose it in the moment it's used ("I read what's on your clipboard" in the activity log), never as a standing permission toggle nobody will ever visit.

---

## 8. Conversation

Conversation is a *mode*, not the product's identity — Mike existing when you're not talking to him is the actual point (§1). The current implementation already gets the important thing right: two typographic registers (what Mike said vs. what he did), not a chat-bubble UI. Keep that. What's missing:

- **No conversation ever survives a restart except as the compressed situation summary.** The raw transcript (`MikeCore.history`) lives in process memory only, capped at 40 turns, gone on quit. This is a real, deliberate gap worth naming precisely: Mike currently has *gist continuity* ("what were we doing"), not *transcript continuity* ("what exactly did we say"). Whether to build transcript persistence is a real product decision, not a bug — see §13.
- **No way to scroll back within a session either**, beyond what's currently rendered in the logbook. Not urgent while sessions are short; becomes real friction the moment Projects (§13) makes sessions span days.

---

## 9. Voice

The real relationship, verified: F6 or "Hey Mike" opens Summon and starts recording; recording auto-stops via a per-session noise-floor calibration (fixed this session — was previously miscalibrated and laggy); transcription is macOS's on-device `SFSpeechRecognizer`, whole-file, not streaming (no partial results while you're still talking); speech output is macOS `say`, sentence-by-sentence as tokens arrive.

**Barge-in exists, but only one direction.** Pressing F6 while Mike is speaking stops him and starts listening — a deliberate, working interrupt. Saying "Hey Mike" while he's speaking does **not** interrupt him: `_wake.suppress()` is called the moment he starts talking and only resumes once he's done. This is a real, specific, fixable gap — true barge-in (start talking over him, he stops) needs the wake-word/VAD path to stay live during TTS playback instead of being suppressed. Worth building; not currently built.

**What makes talking to Mike feel natural, concretely, given what's real:**
- The dial's listening arc is a real amplitude reading, not a loop — already true, keep it.
- Silence-based turn-taking (1.2s of real quiet) rather than a push-to-talk-only model — already true.
- No streaming transcription means no live captions while you talk — the user sees nothing until they stop. This is an honest limitation to communicate (a listening state, not a "here's what I'm hearing" state), not to fake with animation.
- Failure states are already handled distinctly ("no speech detected," "couldn't understand," mic permission) — keep that specificity; a generic "something went wrong" would be worse.

---

## 10. Vision

`Vision.describe_screen()` — one screenshot, one description, tool-invoked (`see_screen`), gated behind the same freshness window as everything else MikeCore tracks (120 seconds). This is **not** continuous screen awareness, and the product should never imply it is. No always-on visual context, no "Mike is watching your screen" ambient claim.

This is the right default for a privacy-first product, not just a current limitation — it should be stated as a *feature*: **Mike looks at your screen only when you ask, and only for that one moment.** The Settings line already says this ("Reads the screen only when asked"). It's correct and should stay a first-class trust signal, not get quietly upgraded to continuous vision later without it being a loud, opt-in decision.

---

## 11. Memory

**This is where the repository has a real surprise in it.** There are two entirely separate memory systems in this codebase, and only one is alive.

- `memory/` (686 lines — `MemoryManager`, `LongTermMemory`, `MemoryAnalyzer`, `MemoryRetriever`, `MemorySearch`) is a more elaborate design — importance scoring, category analysis, semantic-feeling retrieval. It is imported by exactly one other orphaned module (`core/state_manager.py`) and nothing on the live path. **Dead.**
- `brain/memory_store.py` (the real one, wired into `core_runtime.py` and exposed as the `remember`/`recall_memory`/`forget_memory` tools) is a plain SQLite table: content, a category from a fixed set (`preference, person, project, location, workflow, fact`), keyword `LIKE` search, a simple duplicate-merge on save. No embeddings, no vector search, no importance weighting despite the dead package having a field for it.

**Product decision: don't pretend the simple one is the elaborate one, and don't build the elaborate one just because it exists.** Keyword-based memory, made completely legible, is a better product than semantic memory that's mysterious about why it recalled what it recalled. The category taxonomy already in `memory_store.py` is a genuine gift — it's the exact shape a Memory UI needs and doesn't require inventing anything: group by category, show content, show when it was learned, let the user edit or delete inline. No confidence scores, no relevance percentages — either Mike remembers something or he's forgotten it, and the user can always see the whole list.

Memory should feel like **reading a short list Mike keeps about you**, not administering a database. Every entry: what he remembers (his sentence, not a raw field dump), when he learned it, and one tap to correct or forget it. `forget("everything")` already exists as a real, working nuclear option — surface it plainly, don't hide it behind confirmation theater beyond the one dialog any delete deserves.

**Status: engine exists, no UI.** This is the single highest-leverage next build in the entire product — the infrastructure is already correct.

---

## 12. Agency

Two things must stay separated, per the explicit instruction, and the current build already gets this right in one specific place worth preserving: **the dial in `ui/instrument/` shows a trip counter, not a progress bar** — it ticks once per real completed action and never claims to know a total. That decision was made *because* of a measured, specific model limitation (documented earlier in this project): Qwen3 8B sometimes narrates an action in prose instead of calling the tool, especially right after observing a prior tool's result. That's not a UI problem to design around with cleverer copy — it's a real reasoning-model behavior, isolated and confirmed by direct testing.

**What the current model reliably does:** single tool calls, and most multi-step chains when each step is explicit. **What it doesn't reliably do:** author new content immediately after observing a result without occasionally just describing what it would do instead of doing it.

**What this means for product design today:** never render a plan, a step count, or a "Mike is working on 4 things" claim — only completed actions and the one currently running, exactly as built. This is not a permanent ceiling on the product's *ambition* — it's a permanent ceiling on what the *interface may claim*, which is a different thing. If a stronger local model closes this gap later, the interface doesn't need to change at all — it was already honest.

**What Mike should eventually become**, kept separate from the above: a system that can be handed a genuinely multi-day goal ("get this repo shipped") and work it in bounded, checked-in sessions — this requires Projects (§13) and a scheduler (§16), neither of which exist yet, more than it requires a better model. Sequence this after continuity, not before.

---

## 13. Projects / continuity

**The real insight here: Mike already has restart-surviving continuity, and nothing is built on top of it.** `situation_store.py` is a single-row SQLite table holding one global summary, reloaded on every launch. The product experience today is: quit Mike, relaunch, ask him a question — he has the gist of before. That's genuinely rare among local AI tools and isn't being used as a feature anywhere in the UI.

**Proposal: Projects are a named scope, not a new place.** Opening a project is like `cd`-ing into a directory — because, concretely, it *is* one. A project:
- pins a working directory (the thing Mike already half-infers from IDE context and frontmost-app detection, made explicit and durable)
- gets its **own** situation summary row (the single-row table becomes keyed by project id — a small, well-scoped schema change, not a rewrite)
- scopes memory entries tagged to it (the `project` category already exists in `memory_store.py`'s taxonomy — start actually using it)
- scopes the activity log to "what happened in this project" as a filtered view of the same `activity_store` table, not a separate one

**How the user returns to it:** they don't "open the Projects room" — they mention the project, or Mike recognizes the working directory/IDE workspace and asks "still working on X?" the way a colleague would, using the real frontmost-app/IDE-context signal that's already live. Opening Chat scoped to a project is opening Chat with that project's situation summary loaded instead of the global one.

**How they inspect what Mike remembers about it:** History → Memory tab, filtered to the project category — no new surface, an existing one with a filter.

**How they find something Mike created:** this is where Library (§15) would matter, and doesn't exist yet — flagged honestly as a real gap, not solved by pretending folders-and-search is good enough forever.

**Status: requires new substrate** (keying the situation table by project, a `project_id` column on memory and activity rows) **— small, not a rewrite.** This is genuinely the highest-value thing to build after the Memory UI in §11, because it turns an already-working, currently-invisible mechanism into the product's actual differentiator: *Mike doesn't forget what you were doing, and can hold more than one thing at once.*

---

## 14. Activity / history

Built and real: `activity_store.py`, a durable, capped (500 rows) SQLite log written only from real tool outcomes, never from intent. Already surfaced in History. The one gap: it's currently a flat list with day headers — once Projects exist, it needs a project filter, which is a query change, not new infrastructure. No other changes recommended here; this piece of the product already does exactly what it should and shouldn't be made more complicated.

---

## 15. Artefacts / Library

**Does not exist. No tool currently tracks "this file is something Mike produced."** `create_file`/`write_file` write to disk and the action shows up in Activity as a log line — there's no separate registry of artefacts, no way to ask "what has Mike built for me." This is **design only** — worth wanting, not worth building before Projects, because a Library without a Project to organize it by is just a second, worse Finder.

**Recommendation when it is built:** don't invent a new artefact-storage concept — an artefact is just a file, tagged with the activity row that created it (a foreign key on `activity_store`, not a new table). "Show me what you built" becomes a filtered view of Activity where the outcome was a file write, grouped by project.

---

## 16. Schedules

**Does not exist in any form** — no scheduler, no durable queue, no cron-like mechanism anywhere in the codebase. This is the correct thing to leave for last, and for a specific reason worth stating plainly: a schedule means Mike acts **while nobody is at the keyboard**, which puts it in direct, unresolved tension with the confirmation gate that is the product's core safety promise (§3, §19). "Ask before anything destructive" and "run unattended at 9am" cannot both be true without a real policy decision about what an unattended Mike is and isn't allowed to do — and that decision shouldn't be made as a side effect of shipping a calendar feature. **Future. Requires a genuine safety-model decision before any substrate work starts.**

---

## 17. Personalization

Real today: voice on/off, wake-word on/off (`config/preferences.py`, five keys total, deliberately small). Recommend staying deliberately small — personalization should mean "the few things that change how Mike behaves toward you specifically," not a settings tree. Voice selection/rate exist as preference keys already (`voice_name`, `voice_rate`) but have no UI — small, real, low-priority addition once Settings has room for it.

---

## 18. Privacy

The product's actual, defensible claim, verified: no network calls in the live inference/tool path; the model runs on-device via Ollama; the one thing Mike reads from the outside world on request (the screen) is fetched fresh each time and held for 120 seconds, never persisted. This should be *louder* in the product than it currently is — not as a legal footnote but as the plain-fact statement already in Settings ("Everything stays on this Mac / no network calls"), possibly worth a one-time, unmissable moment at first launch (§25) rather than only living in a settings row someone has to go looking for.

---

## 19. Safety

The gate is real, narrow, and correctly scoped: five action types (`write_file`, `delete_path`, `run_command`, `run_background`, `ide_apply_edit`) always stop and ask, described in plain language, resolved through the same `threading.Event` mechanism regardless of which surface (Home, edge, invoke line) the confirmation is shown on. This is good architecture — one gate, many faces — and should stay exactly that shape as new surfaces get added, rather than each surface growing its own confirmation logic.

**What's missing is visibility into consequence, not more gates.** Right now a confirmation shows *what* Mike wants to do (`run rm -rf node_modules/.vite`) but not *why* or *what happens if it goes wrong*. A small, real improvement: when a confirmation is denied, that denial is already logged to Activity (verified — denied actions show up as failed rows) — make that legible as a trust signal ("you can see everything I asked and everything you said no to"), not just incidental logging.

**What Mike does if he makes a mistake:** currently, nothing beyond a plain error message and the action being logged as failed. There's no "undo," and for the current gated action set (file writes, deletes, commands), a generic undo isn't really possible to build safely — a file write can be diffed and offered as a revert *if the write tool captured a before-state*, which it currently doesn't. Worth a scoped addition (capture the previous content before `write_file` overwrites, offer "revert this" from the Activity row) rather than a general undo system.

---

## 20. Permissions

There is currently no dedicated "permissions" surface distinct from Settings' static "what Mike may do" statements — and that's mostly correct, because the actual permission model is binary and architectural (the confirmation gate), not a matrix of togglable scopes. The one place a real permissions *decision* is missing: **folder/path scoping.** Mike can currently read/write/delete anywhere the filesystem tools can reach, gated only by the confirmation dialog's presence — there's no boundary like "only within this project folder." Whether to add one is a genuine, unresolved product question, not an oversight: a boundary adds real safety but also real friction ("why won't Mike touch my Downloads folder"), and should be decided deliberately rather than defaulted into.

---

## 21. Integrations

**Real and unexposed:** `tools/email/` is a fully built package — Gmail OAuth, a client, actions — that has **no tool declaration in `core_tools.py`**. The model cannot call it. This is a step earlier than "engine exists, no UI" — it's *engine exists, not even wired to the reasoning loop.* A real, scoped decision point: wiring it in is small (one more `FunctionDeclaration`, gated in `_CONFIRM_ACTIONS` for anything that sends mail), but "Mike can read and send your email" is a significant trust escalation that deserves the same deliberate, visible treatment as any other new reach — not a quiet addition.

**Real and live:** the IDE bridge (`ide/manager.py`, VS Code only today, architected for other editors without touching the brain/tools/UI layers — worth preserving that seam exactly as-is). No other integrations exist; nothing else should be implied.

---

## 22. IDE presence

Today: invisible infrastructure that feeds context (file, workspace, diagnostics, selection) into the situation summary and the Home context label — a real, working D4 in spirit, with zero visible presence *inside* the editor itself. A genuinely visible embedded presence (an in-gutter indicator, an inline suggestion surface) is real future product, not close to built, and shouldn't be implied as more real than it is. The bridge architecture (`ide/contracts.py`'s adapter pattern, one adapter per editor) is the right foundation for it whenever it's built.

---

## 23. Notifications

**Does not exist.** No OS notification-center integration anywhere. Given the edge strip already serves the "something happened, glance at it" role while Mike is running, a system notification only earns its place for the specific case the edge strip can't cover: **something finished while Mike wasn't visible on screen at all** (minimized, or the user stepped away). Low priority; small addition once it's clearly needed, not before.

---

## 24. Settings

Already close to right in shape (Behaviour / Reach / Privacy, per §5) and should resist growing into a tree. The test for whether something belongs in Settings: **is this a standing choice the user makes once, or a moment-by-moment decision?** Standing choices (voice on/off, wake word on/off) belong here. Moment-by-moment decisions (approve this specific action) never should, and nothing in the current build makes that mistake.

---

## 25. Onboarding

**Does not exist in any form** — `MikeWindow.__init__` starts the runtime, registers the hotkey, and shows Home; there is no first-launch state distinct from every other launch. This is a real gap for a product that wants to be trusted immediately: the strongest thing Mike has to say for himself (local-only, asks before anything destructive, remembers what you tell him) is currently said nowhere on first contact.

**Recommendation:** not a multi-step wizard — one honest screen, shown once, that states the three real facts from §1 in plain language, confirms the microphone/wake-word permission if the user wants voice, and ends by putting the cursor in the composer. No feature tour, no fake sample conversation. The product's trust story is short enough to fit in four sentences; say them once and get out of the way.

---

## 26. Error / recovery experience

Real today: connection failures (Ollama unreachable), timeouts, and generic exceptions are each turned into a specific, readable sentence (`_humanize_error` in `ui_controller.py`) rather than a raw traceback — good, keep that specificity as the pattern for every future error surface. Voice failures are similarly specific ("no speech detected" vs. "couldn't understand" vs. a permission problem) rather than collapsed into one message.

**Missing:** any recovery *action*, not just a readable message. "I couldn't reach the local model" should offer to check whether Ollama is running, not just say so. This is a small, real addition — diagnostics (§ below) feeding directly into the error surface rather than living in a separate, harder-to-find place.

**Diagnostics as a concept doesn't exist as a surface at all today** — no "is Ollama running, is the model pulled, is the mic permission granted" self-check anywhere. Worth building as the thing an error state offers to run, not as a standing settings page nobody visits until something's already broken.

---

## 27. Platform strategy

Mac is not just the reference platform today — large parts of the implementation are macOS-specific by design and by real dependency: Carbon for the global hotkey (chosen specifically to avoid an Accessibility permission prompt), `SFSpeechRecognizer` and `say` for voice, `osascript`/`Quartz` for environment awareness. None of this is a temporary shortcut — it's the reason the product currently needs no special permissions to feel instantly present.

**The honest split for a future multi-platform Mike:**
- **Shared, platform-independent today:** the reasoning loop, the tool contracts, the safety gate, memory/activity/situation storage (all plain SQLite/JSON), the visual/interaction language once it's chosen.
- **Platform-specific, and should stay that way rather than forcing sameness:** the global-invocation mechanism (Carbon has no Windows/Linux equivalent — each platform needs its own idiomatic answer, not a lowest-common-denominator hotkey library), voice (each OS has a different "good enough, on-device, free" answer), environment awareness (AppleScript/Quartz have no direct Windows/Linux equivalent).

**Recommendation:** don't design a cross-platform abstraction layer speculatively. The tool/runtime/storage layer is already platform-agnostic by accident of being plain Python + SQLite — that's the real asset to protect. Everything that touches the OS directly should stay a thin, swappable adapter (mirroring the IDE bridge's own adapter pattern) written *when* a second platform is actually being built, not before. Mobile/web are genuinely future — a "companion" mobile app reading the same local SQLite stores over a paired connection is a coherent future shape; a full mobile Mike (running the model on-device) is not, given current on-device model constraints.

---

## 28. Visual / interaction direction

Three visual languages were built and abandoned or kept this project: an orb-based "Home V1" (rejected — read as a generic chatbot/Siri empty state), a caret-based identity (rejected — described as failing to feel premium), and the current instrument/dial language (kept, still evolving under direct feedback this session). I'm not re-opening that decision here — it's live, it's had real iteration, and the user has been actively shaping it turn by turn. What I'll say plainly: whatever the final visual language is, the things that have proven themselves *independent of which skin was on top* are the real assets — the depth ladder (§4), the two-register typography (said vs. did), a single object standing in for Mike's presence at every size, and state communicated through *what's real* (a trip counter, not a progress bar) rather than through decoration. A fourth visual rewrite, if one happens, should inherit all four of those unconditionally.

---

## 29. Current capability map

| Capability | State |
|---|---|
| Local LLM reasoning (qwen3:8b) | **BUILT** |
| Filesystem, terminal, browser, system tools (17 of 21) | **BUILT** |
| Safety confirmation gate | **BUILT** |
| Situation summary (cross-restart continuity) | **BUILT**, unused beyond the current session |
| Activity log | **BUILT** |
| Keyword memory (`remember`/`recall`/`forget`) | **BUILT**, engine only — no UI |
| Vision (single-shot, on request) | **BUILT** |
| Voice (record, calibrate, transcribe, speak) | **BUILT** |
| Wake word | **BUILT** |
| Global hotkey invocation | **BUILT** |
| Edge / Summon / Dwell surfaces | **BUILT** |
| IDE bridge (VS Code) | **BUILT**, invisible-infrastructure only |
| Voice barge-in via keypress | **BUILT** |
| Voice barge-in via speaking over Mike | **ENGINE EXISTS / NO EXPERIENCE** (wake detector is suppressed during TTS) |
| Memory UI | **DESIGN ONLY** |
| Projects | **DESIGN ONLY** (this document) — real substrate (situation summary) exists, unused |
| Email | **ENGINE EXISTS**, not wired to the model at all |
| Diagnostics / recovery actions | **DESIGN ONLY** |
| Onboarding | **DESIGN ONLY** |
| Artefact tracking / Library | **REQUIRES NEW SUBSTRATE** |
| Schedules | **FUTURE** |
| Notifications | **FUTURE** |
| Folder-scoped permissions | **FUTURE** (undecided, not just unbuilt) |
| Multi-platform | **FUTURE** |
| Embedded (visible, in-editor) presence | **FUTURE** |

---

## 30. Future capability map

Ordered by how much they depend on something else in this list:

1. **Memory UI** — depends on nothing new; the engine is complete.
2. **Project-scoped continuity** — depends on keying `situation_store` and tagging `memory_store`/`activity_store` by project id. Small schema change.
3. **Onboarding + diagnostics** — depends on nothing new; assembles existing error/state signals into one first-run moment and one self-check.
4. **Voice barge-in (speak-over)** — depends on reworking wake-word suppression during TTS; isolated to `ui_controller.py` + `wake_word.py`.
5. **Artefact tracking / Library** — depends on Projects existing first (an artefact without a project to belong to is just a file).
6. **Email as a real tool** — depends on nothing technical; depends on a deliberate trust decision.
7. **Undo-by-revert for file writes** — depends on capturing before-state at write time; isolated to `core_tools.py`.
8. **Schedules** — depends on a resolved policy for unattended confirmation, which nothing else on this list unblocks; it's a decision, not a dependency chain.
9. **Multi-platform** — depends on nothing on this list; depends on demand.
10. **Visible embedded (in-editor) presence** — depends on the visual/interaction language (§28) being settled enough to shrink into a gutter.

---

## 31. Recommended implementation sequence

1. **Memory UI.** Zero new substrate, highest immediate trust payoff — "what does Mike know about me" is the single most-asked question of any assistant, and Mike can already answer it honestly; nobody can see the answer yet.
2. **Onboarding + diagnostics.** Small, self-contained, fixes the fact that Mike's strongest asset (local-only, asks first, remembers honestly) is currently said nowhere.
3. **Project-scoped continuity.** The real differentiator. Turns an already-built, currently-invisible mechanism (restart-surviving situation summary) into the thing that actually separates Mike from every stateless chat-with-your-code-editor tool.
4. **Voice barge-in.** Small, isolated, closes the one interaction gap that makes talking to Mike feel less natural than it already mostly does.
5. **Undo-by-revert.** Small, isolated, directly strengthens the safety story from §19 with almost no new surface area.
6. Everything else — Library, email, schedules, permissions scoping, multi-platform, embedded presence — waits. Each has either a real unresolved decision attached to it (schedules, permissions, email) or a real dependency on something above it (Library on Projects, embedded on the settled visual language). Building any of them first would be building on a foundation that doesn't exist yet.

---

## Strongest recommendation

**Stop treating Mike as a UI problem.** Three visual rewrites in one project is not evidence that the visual direction is hard to find — it's evidence that the visual direction was never the thing actually missing. Every rewrite kept the same skeleton (the depth ladder) and the same honesty rules (no fake progress, no fake plans) because those were already right. What's been sitting unbuilt the entire time is a memory the user can see and a continuity the user can *feel* — and both of those are, right now, sitting nearly complete in the backend, one UI screen and one small schema change away from being real.

Ship the Memory room. Then make the situation summary project-aware. Those two things, together, are what would make someone say "he actually remembers" instead of "it's a nice-looking chat app" — and neither one requires deciding what Mike looks like ever again to be true.
