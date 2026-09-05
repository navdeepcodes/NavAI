# Filesystem access — a proposal, not an implementation

## The hypothesis, checked against the actual code

Confirmed. Today there is no filesystem scoping at all — only one gate, and
it isn't about *where*.

- `tools/filesystem/path_utils.resolve_path()` will resolve and hand back an
  absolute path anywhere the OS lets this process read or write — `~/Desktop`,
  `/etc`, another project entirely, a sibling user's home directory. No
  allowlist, no denylist, no boundary of any kind.
- The only thing standing between "the model decided to write/delete/run
  something" and it happening is `brain/core_tools._CONFIRM_ACTIONS` — one
  gate, keyed purely on *action type* (`write_file`, `delete_path`,
  `run_command`, `run_background`, `ide_apply_edit`), asking "may I do this
  one thing," never "should I be working in this area of your disk at all."
- `brain/projects.py` (built this session) already gives Mike a real notion
  of "the folder you're currently in" — resolved automatically from the IDE
  bridge's `workspace_root` — but today that's used only to tag memory and
  situation continuity. It carries zero enforcement. Mike can write outside
  the attached project with exactly the same one-line prompt as writing
  inside it.
- There's a second, dead permission scaffold already in the repo —
  `tools/permissions/` (`PermissionManager`, `SAFE`/`CONFIRM`/`BLOCKED` sets
  keyed on old tool names like `delete_file`/`run_terminal`) — wired to an
  orphaned parallel dispatch system (`core/tool_executor.py`,
  `services/tool_executor.py`, `tools/tool_registry.py`) that the live path
  (`brain/core_tools.py` → `core_runtime.py`) doesn't call. Same pattern as
  the dead `memory/` package the blueprint already flagged — a second
  half-built permission system already exists and already doesn't run.

So: not "underdeveloped," genuinely absent. And it's exactly as load-bearing
as the hypothesis said — it's the thing computer agency, projects, file
operations, future schedules, and trust all sit on top of, and right now
none of them have anything under them but a single "are you sure?" per
action, with no memory and no boundary.

## Why this before the rest of the blueprint

Email, notifications, schedules, IDE presence, and Library all *add* new
things Mike can reach. Every one of them inherits whatever the filesystem
access model looks like at the time — a scheduled/unattended action in
particular is far riskier without a boundary, because there's no human
mid-task to catch an out-of-scope path the way today's confirm prompt at
least gives a chance to. Building any of them on top of "no scoping, ever"
means either re-deciding this question under the pressure of a half-built
feature, or building it five times, slightly differently, once per feature.
This is the one decision that's a prerequisite for the rest rather than
parallel to them.

## The proposal

Reuse what already exists — `projects.py`'s workspace concept and the
`path_utils.SPECIAL_PATHS` list — rather than inventing new machinery.
Two independent, small questions instead of one fuzzier one: the existing
gate keeps asking *"may I do this action,"* and a new, second check asks
*"is this somewhere Mike's already allowed to work,"* asked first.

**What can Mike access by default?**
Unrestricted, as today, within Desktop, Documents, Downloads, Pictures,
Movies, Music — already named as Mike's understood "home turf" in
`path_utils.SPECIAL_PATHS` — plus whatever project folder is currently
attached via the IDE bridge. *Reading* elsewhere stays as it is now (low
risk, already unconfirmed). *Writing, deleting, or running* elsewhere is
what the new check applies to.

**How does project/workspace scoping work?**
It's `projects.current()`, unchanged. The moment the IDE bridge reports a
`workspace_root`, that folder is in scope automatically — no picker, no
manual "add project" step, exactly the zero-UI resolution already built for
memory/situation.

**When does Mike ask for access?**
Unchanged for everything already in scope — same one-line confirm as today.
A new prompt fires only the first time a write/delete/run targets a path
outside default scope: *"Mike wants to work in ~/SomeOtherFolder too —
Allow / Just this once / Deny."* Same `ConfirmStrip` widget, not a new
dialog type.

**What does the user see?**
The same confirm strip, and — once granted — that folder listed under
Settings → "Where Mike can act," a section that already exists in
`home.py._fill_settings()` (today it only shows the IDE bridge's connection
status). This extends a screen that's already there rather than adding one.

**How is access revoked?**
A granted folder is one row in a small table in the same SQLite file as
everything else. Settings lists it; clicking removes it — same interaction
language as "forget" already is in the Memory tab.

**Project, folder, application, or global?**
Folder-level. Matches the one path-shaped concept that already exists
(`workspace_root`) and matches how a person actually thinks about "the
places Mike is allowed to work" — not per-file (too granular to reason
about), not per-application (Mike acts on paths, not app identities), not a
single global switch (too coarse to trust).

**How does this interact with the existing confirmation gate?**
Additive, not a replacement. `_CONFIRM_ACTIONS` still fires exactly as it
does today for every write/delete/run. The scope check is asked first and
separately: in scope → behaves exactly as today; out of scope → the
one-time folder grant appears, and once granted, it's simply in scope from
then on, with the normal confirm/deny gate as the only thing left. Two
small, separately-reasoned checks, not one bigger and blurrier one.

**What happens on an inaccessible path?**
Mike says so plainly, in his own voice — "I don't have access to that
folder" — rather than surfacing a raw error, matching the
`_humanize_error()` pattern already built this session for Ollama
connectivity failures. This covers both a user "deny" and a real OS-level
refusal (see next).

**How does this work naturally on macOS?**
Two real constraints to respect rather than fight. First, macOS's own TCC
protections (Photos, Mail, Contacts, another app's sandboxed container) sit
below anything Mike decides — if the OS refuses the raw syscall, no app-level
grant changes that, so this model stays a layer *above* TCC, not a
replacement for it. Second, this app isn't a sandboxed/notarized bundle
today, so there's no native `NSOpenPanel`-style folder picker to hook into —
the grant flow is Mike's own UI and should read that way, not pretend to be
a system dialog it isn't.

**How does this stay simple for a normal user?**
The whole model compresses to one sentence Mike can say for himself: *"I can
work freely in your everyday folders and whatever project you have open —
anywhere else, I'll ask first, and you can see and remove any place I've
been given access to in Settings."* No tiers, no per-app rules, no path
syntax exposed to the user — the same "things you've said yes to, plainly
listed, one click to undo" framing the Memory tab already uses.

## What this is not

Not a sandbox, not a replacement for the action-type confirm gate, not a new
screen, not a rebuild of `tools/permissions/` (that scaffold stays dead —
its tool-name keys don't even match the live dispatch table). No code has
been written for this. If this direction looks right, the next step is
naming the smallest first slice — most likely just the read side of the
scope check (log what would have been out-of-scope, no enforcement yet) to
see how often it would actually have fired before building the grant UI.
