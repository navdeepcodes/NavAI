# Mike — UI/UX Redesign, Phase 1 (design only)

Full exploration: `mike-ui-phase1.html` (open in a browser).

Status: **design complete, nothing implemented.** No file outside `design/` was
touched. Backend, Mike Core, Agency, tools, memory, voice, vision and the VS Code
bridge are untouched and remain frozen.

## Diagnosis of Home V1

Captured from the running widget tree, not from memory. Nine faults, all downstream
of one decision: Mike was built as *a place you go*. The composition is a chatbot
empty state (centred mark, greeting, pill composer, footer links); the orb is the
most-taken mark in AI software; ~55% of the frame is unresourced black; the
brightest object on screen is the send button; nothing distinguishes what Mike
*said* from what Mike *did*; and nothing on screen belongs to this specific
computer.

## Depth model

    D0  Ambient      running, no pixels — where Mike spends 99% of its life
    D1  Edge         temporary opening at the screen edge; never takes focus
    D2  Invocation   ⌘⇧Space / wake word; one line; takes focus because you asked
    D3  Home         where you dwell: record, memory, conduct
    D4  Embedded     inside the editor (bridge exists, presence does not)

Escalation rule: Mike may deepen **only on user action**. D1 work finishes at D1.

## Information architecture — four rooms

| Room     | Question                    | Contains                                        |
|----------|-----------------------------|-------------------------------------------------|
| Now      | what's happening?           | conversation, live work, composer, context      |
| Record   | what did Mike do?           | action log, results, failures, artefacts        |
| Mind     | what does Mike know?        | memory (live), projects + schedules (future)    |
| Conduct  | how does Mike behave / what may it touch? | manner, limits, reach         |

Library folds into Record (artefacts stay attached to the action that made them).
Projects/Schedules live in Mind — things Mike *holds*, not things Mike *did*.

## Three directions

1. **SEAM** — Mike is a change in the shape of the display. Superb at D1, thin at D3.
2. **CARET** — Mike is a living cursor. Type-first; prose = said, mono = did.
3. **CHAMBER** — Mike is light in a dark room. This is what V1 attempted.

## Recommendation: CARET

1. Unclaimed — no AI product uses the caret; orbs and waveforms are taken.
2. Promises attention, not autonomy — honest given the Qwen3 8B narration limit.
3. Survives every depth unchanged: 3px in a gutter, 34px at Home.
4. QPainter renders hard-edged rects and text well; blur and gradient badly —
   which is visibly why V1 looks cheap. This removes the failure mode.
5. Solves said-vs-did through type register alone: no cards, badges or icons.
6. Absorbs SEAM's edge behaviour (geometry along one axis) as its D1 model.

CHAMBER rejected on evidence: we built it, it is the thing in the screenshots,
and its failure was technical as much as conceptual.

## Capability honesty

Backed by real code today: activity log (`brain/activity_store.py`), memory
(`brain/memory_store.py`, `memory/`), situation (`brain/situation_store.py`),
safety gate, VS Code bridge, voice, wake word, shortcut.

**No backing store exists** for Projects, Schedules or Library. They are designed
so the IA has room for them; each needs its own persistence before anything is
drawn in the app. Schedules additionally needs a policy for the confirmation gate
when nobody is at the keyboard — unattended agency and the safety gate are in
direct tension, and that is unresolved.

## Never render

Progress bars · step counts · speculative future steps · "working autonomously" ·
completion language before a tool returns · queues of pending actions.
All six require knowledge Agency V2 does not have.
