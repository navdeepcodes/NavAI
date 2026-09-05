# General computer interaction

Mike could already read files, run commands and navigate to URLs. What it had
no way to do was operate an interface that exposes no API — click a control,
type into a field, move between windows. This is that layer.

Everything below is measured on this machine (16 GB, macOS 24.6, qwen3.5:9b)
on 2026-09-05. Where something is not implemented it says so.

## Shape

    computer/
      base.py      canonical types, ComputerController ABC, irreversibility rule
      macos.py     AXUIElement (read) · CGEvent (drive) · CGWindowList (windows)
      session.py   element references, staleness, tool-facing results

Nothing above `base.py` names a platform API, and a test enforces it: if
`CGEvent`, `AXUIElement`, `NSWorkspace` or `Quartz` appears in the runtime,
the suite fails. `get_controller()` raises on Windows with a message naming
what an implementation must provide, rather than returning a stub whose
actions would silently do nothing.

Seven primitives are declared to the model: `see_ui`, `click_element`,
`type_text`, `press_keys`, `scroll_ui`, `list_windows`, `focus_app`. They are
deliberately small. There is no `send_email` tool and there should never be
one — the moment application workflows become tools, Mike stops being a
general agent and becomes a collection of scripts.

## Observation hierarchy

1. **Accessibility tree** — 0.002–0.03s, returns named controls with roles,
   values and enabled state.
2. Browser DOM / deterministic APIs, where a better semantic source exists.
3. **Vision** — 4–7s, for surfaces the tree cannot describe.

The gap is three orders of magnitude, so the ordering is not a style
preference. `see_screen`'s own declaration tells the model this and names
`see_ui` as the alternative.

## Why references, not coordinates

`see_ui` returns `[el7] button 'Send'` and the model acts on `el7`. A model
choosing pixel coordinates from a screenshot is guessing, and a guess two
pixels off clicks the wrong control with complete confidence. A reference
resolves against an element that was really there, with real bounds, and
fails loudly when it is not.

Three ways resolution fails on purpose:

- **No observation yet** — act before looking and you are told to look.
- **Stale** — references expire after 120s, because interfaces move and
  resolving an old reference against a new screen clicks whatever is there now.
- **Unusable area** — VS Code reports its editor as `0x14`, zero pixels wide.
  Clicking the "centre" of that lands on a boundary and silently misses, so it
  is refused with a message saying what to try instead.

## Safety

The existing confirmation gate is unchanged. Computer control adds one rule:
a click is gated by **what it targets**, not by being a click.

Gating every click would make the agent unusable and train the user to click
through prompts, which is worse than no gate. So the label decides:

    gated       Send · Submit · Delete · Move to Trash · Buy · Pay · Publish · Post
    not gated   Cancel · Save Draft · Back · Compose · Reply · Attach · Search · OK

It is a property of the interface, so the same rule protects a Send button in
any mail client rather than being a per-application list. Substrings do not
match — `Sender name` and `Resend later` pass through. A click by raw
coordinates is always gated, because nothing verified what is there.

Confirmation text names the target: *"This clicks button 'Send' — a 'send'
action that cannot be undone."*

**Limit, stated plainly:** an unlabelled button cannot be judged this way.
This narrows the blast radius; it does not eliminate it.

## Electron

Electron apps returned zero elements. The cause was **not** Electron
withholding its tree.

Chromium does expose `AXManualAccessibility` as an opt-in, and Mike now sets
it — it is the correct request for apps that gate on it. But it was not the
fix: the Claude desktop app reported that attribute as `False` afterwards and
served a full tree anyway.

The real defect was window selection. Asking for the focused window fails when
the app is not frontmost, and the fallback took `windows[0]` — which in
Electron is an untitled zero-child helper window. The interface was one window
along the whole time. Selection now prefers focused, then main, then the
window that actually has children and a title.

A second defect surfaced with it: `observe()` returned `status: success` with
zero elements when the application was not found at all, so a lookup failure
read as an empty screen. It reports an error now.

Verified against VS Code: 45 addressable controls, correct roles
(button/checkbox/tab/radio/text_area/link), labels intact, `Go Forward`
correctly reported disabled, references resolving, and typed text landing in
the editor.

## Two macOS defects worth recording

Both presented as "input does not work" and neither was about input.

**`NSWorkspace.frontmostApplication()` goes stale.** It answers from a cache
refreshed by run-loop notifications, and a tool call has no run loop — so it
returns whatever was frontmost when the process started, forever. Measured:
after switching apps three times it named the first app every time while the
CoreGraphics window list tracked each change. `frontmost_app()` reads the
window list.

**`activateWithOptions_` does not activate another application.** Modern macOS
refuses cross-application activation from a process that is not frontmost; the
call returns without doing anything and the target's `isActive` stays `False`.
Activation now falls back to LaunchServices (`open -a`), which needs no extra
permission, and then raises the target window through the accessibility API.

That last step matters on its own: activating an application is not the same
as giving one of its windows keyboard focus. An app can be frontmost with no
key window, and then synthetic keystrokes go nowhere while every check reports
success — `focus_app` said "now frontmost", `type_text` said "typed 11
characters", and the document stayed empty.

## Vision latency, measured

Baseline, prose prompt at `num_predict=150`: **~10.5s** warm, and the answer
opened with "This is a screenshot of a macOS desktop environment".

The path, profiled:

    screencapture              0.156s
    resize to 640px            0.067s
    PNG encode                 0.006s
    base64                     0.000s
    ------------------------------------
    preprocessing total        0.229s
    image + prompt eval        0.2-0.3s
    generation                 1.9-4.9s   <- everything

Generation runs at a flat ~15 tokens/second, so **latency is output length**.
Nothing else is worth touching:

    num_predict  150   4.8s      prompt eval 0.2s   generation 4.4s
    num_predict   48   4.0s      prompt eval 0.3s   generation 3.6s
    num_predict   24   2.3s      prompt eval 0.3s   generation 1.9s

Image size is not a lever either. Dropping 640 → 448px halves the prompt
tokens (281 → 147) and did not run faster; 640 stays.

**Current state:** a UI control list costs **4–7s** depending on machine load,
against ~9–10s for prose. The structured prompt is also more useful — it
returns `text field "Type / for commands"` where prose returned a paragraph
about the desktop.

**Is that fast enough for interactive computer use? No.** A 4–7s look is
tolerable once in a task and unusable in a loop that needs to observe after
every action. On this hardware, a 9B vision model generating at ~15 tok/s
cannot get there, and no preprocessing change will alter that — the ceiling is
generation speed.

What makes the layer usable anyway is that vision is not the observation
mechanism. The accessibility tree answers the same question in 0.002–0.03s and
covers native apps, Electron apps and browser chrome. Vision is reserved for
what the tree genuinely cannot describe.

## Not implemented

- **Windows.** The interface is defined; there is no implementation and
  `get_controller()` says so rather than pretending.
- **Browser DOM.** Level 2 of the hierarchy. Browser windows are currently
  read through the accessibility tree like any other app, which gives chrome
  and some page controls but not the DOM.
- **Region capture / change detection.** Would reduce vision calls but not
  their cost; generation dominates, so cropping is not the win it appears.
- **A faster vision model.** Deliberately not added. The measurement above is
  the case for it, not a hunch — but adding a second model is a real
  architectural cost and should be a decision, not a side effect of this work.

## Behaviour change worth knowing

Vision used to be described as something Mike does only when the user asks.
It is now also the fallback for surfaces the accessibility tree cannot
describe, which means Mike may capture the screen on its own initiative during
a computer-use task. `tests/test_vision_integration.py` was updated to assert
the guarantee that still holds — that vision is never the default or casual
way to inspect an application — rather than the one that no longer does.

---

# Phase 2 hardening

A systematic pass over the whole existing capability surface rather than one
workflow. Everything below was found by exercising the code, not by reading it.

## Reference identity

References were validated by age alone. A reference seconds old still
resolved -- to whatever now occupied that position. That is how subject text
was typed into a recipient field: an autocomplete list opened between
observing the compose window and clicking Subject.

They are now re-resolved by identity at action time. The remembered element
supplies role and accessible name; the interface is observed again; the
control carrying that identity *now* is acted on.

Identity is `(role, casefolded name)`. It deliberately excludes value and
position -- a field typed into is the same field, a control that moved is the
same control. Position is a tiebreaker only.

    control moved                  found at its new position
    value changed                  still valid
    nothing matches                refused, naming what is there now
    several match, position helps  resolved to the one still in place
    several match, position does not  refused as ambiguous
    unnamed control that moved     refused (role alone is not identity)
    window unreadable              refused

Measured against two real pages where a row is inserted above a field:

    naive click at the old position would hit: 'Suggested contact'
    Mike clicked: text_field 'Subject' at its new position
    text landed in: Subject

## Tool contract

A sweep of all 41 declared tools found 18 places where a call that could not
succeed was accepted: four argument-less tools swallowed unknown parameters,
and fourteen accepted strings where the schema declared an integer or array.

Both matter for the same reason as the `path`/`cwd` bug this file already
records: a parameter that is accepted and dropped makes the tool do something
other than what was asked.

Now enforced from the same schemas the model is given, so a new tool is
covered the day it is declared. Lossless coercion is still allowed --
`timeout="30"` is unambiguous and models produce it constantly -- while
`pid="soon"` is refused.

## The safety hole

`write_file` was gated. `create_file` wrote arbitrary content to an arbitrary
path with no confirmation, and silently overwrote whatever was there. A model
wanting to write without a prompt only had to pick the other tool, and it need
not have been doing so deliberately for a user's file to be gone.

Gating every file creation would have been the wrong fix: writing a genuinely
new file destroys nothing, and a prompt that fires constantly is one people
learn to click through. So the gate stays where the consequence is, and
creation refuses to become an overwrite.

## Documents

Two failures were being reported as successes:

    empty .csv   status=success, body "Could not extract text from this file"
    .png         status=success, body starting with the PNG header bytes

The first puts an apology where the model expects content, with no way to tell
it apart from a document that says that. The second hands the model noise to
pattern-match against. Both now raise `DocumentUnreadable`, and the runtime
distinguishes a wrong path (retryable) from a broken file (not).

## Processes

Background processes were being killed correctly, but their registry entries
were not cleared, so a listing after teardown described dead servers as
session state. Dead entries also accumulated for the life of the session.
Both fixed; `list_processes` now also reports under `result` like every other
tool, instead of logging a successful listing as "Done".

`recall_memory` had the same reporting gap -- data reached the model through
the full tool payload, but anything reading the documented key saw nothing.

## Test isolation

A test called the live Gmail send executor, guarded by "skip if credentials
work". It was silent until authentication started working, and then every full
run sent a real email. Ten went out before it was caught.

Detection by reading the code was not enough, because the code looked
reasonable. The live path is now severed suite-wide by an autouse fixture; a
test that reaches it raises. Opting in requires `@pytest.mark.sends_real_email`
and nothing currently does. Verified by writing a deliberately bad test: it
failed, and a mailbox query confirmed nothing escaped.

Real-application E2E tests are separated behind `MIKE_RUN_APP_E2E=1`. They
drive TextEdit and VS Code and contend with whatever else is on screen, so
inside a full suite they failed intermittently for reasons unrelated to the
code. A test that fails a third of the time teaches people to ignore failures.
The same logic is covered deterministically by stubbed controllers.

## Recovery, characterised

Given a task naming a file that does not exist:

    two plausible candidates present  -> reports the real directory contents
                                         and asks which was meant
    one candidate present             -> finds and reads it unprompted

Neither invented a figure. The first is conservatism rather than a recovery
failure, and the distinction was worth measuring rather than assuming.

---

## Typing had no idea where it was going

Found while running the browser-form benchmark for repeats. Mike opened the
page in Safari, typed the person's name, and the name landed in the **address
bar** — the URL read `registration_form.htmlJordan Lee` while the Full name
field stayed empty. Focus had never left the address bar after the page
loaded, and nothing in the chain noticed.
(`design/evidence/typing_went_to_the_address_bar.jpg`)

Every step reported success, because `type_text` synthesised keystrokes and
said "typed 11 characters" without ever asking where they went. It is the
same shape as the silent click fixed earlier in this phase: an action that
cannot fail because it never checks.

The mistake in the design was treating typing as aimed by the previous
click. It is not. **Typing is aimed by keyboard focus**, and focus is not
always where the last click landed — a page can steal it back, a click can
land on a label rather than its input, or focus can simply never have moved.

So focus is now read, not assumed. `ComputerController.focused_element()`
returns the control that will receive the next keystroke, and `type_text`
reads it before typing and again afterwards, reporting:

```
typed 10 characters into text_field 'Full name', which now reads 'Jordan Lee'
```

and when the target is not somewhere text goes:

```
typed 10 characters into button 'Submit application' — note that button is
not a text field, so the keystrokes may not have gone where you intended
```

and when the platform cannot answer at all:

```
typed 10 characters — but the focused control could not be read, so where
the text went is unverified. Use see_ui to check.
```

Three properties matter here. The report names a real control read from the
accessibility tree, not the one that was aimed at. It includes the field's
resulting value, so the model can see its own text arrive rather than infer
it. And it never claims placement it could not verify — the base class
returns `None` for platforms that cannot read focus, and the message degrades
to saying so.

Mike still decides what to do about a bad landing. The runtime's job was only
to stop hiding it.

### Why the click was innocent

The first diagnosis of that failure was wrong, and the correction is worth
recording because it is the same trap this project keeps walking into from
the other direction.

Clicking the field and then reading focus appeared to show the click landing
without taking focus — three times in a row, with the field staying empty.
That looked like a serious bug in synthetic clicking.

It was an artifact of the investigation. An `osascript` probe run moments
earlier had raised a macOS automation-permission dialog, positioned at
(725, 206) and 260×296 points in size — directly over the field at (865, 234).
Every "click on the text field" was landing on that dialog.

With the dialog cleared, the same sequence works exactly as designed:

```
click : left click at (865, 234) on text_field 'Full name'
focus : [focus] text_field 'Full name' (focused)
type  : typed 10 characters into text_field 'Full name', which now reads 'Jordan Lee'
```

So the click mechanism is sound, and the original address-bar failure was
Mike typing before it had focused anything — which is precisely what the new
reporting now makes impossible to miss.

The general lesson, third time in this project: **a window from another
process can silently intercept a click**, and nothing in the stack notices.
The focus check catches the consequence rather than the cause, which is the
best that can be done without owning the window server. It is also why the
check reports rather than fails: an obstructed click is a real event the
model should reason about, not an exception to be swallowed.
