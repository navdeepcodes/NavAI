# Mike

A local-first desktop AI assistant for macOS — runs on-device, listens for a
wake word, sees the screen when asked, and can act: read and write files, run
commands, drive other applications through the accessibility layer, work on
spreadsheets, send mail, and edit code through an editor bridge. The reasoning
never leaves the machine.

## Stack

- Python + [PySide6](https://doc.qt.io/qtforpython/) (native Qt UI, custom
  `QPainter` rendering — no Electron)
- [Ollama](https://ollama.com), running `qwen3.5:9b` locally, for reasoning,
  tool-calling, and vision — one model serves as both brain and eyes
- macOS accessibility (`AXUIElement`) and synthetic input (`CGEvent`) for
  operating other applications
- macOS-native audio/speech (`say`, `SFSpeechRecognizer` / `NSSpeechRecognizer`,
  Carbon global hotkeys) — no cloud TTS/STT
- SQLite for memory, activity, and situation state
- openpyxl for spreadsheets

## Structure

```
brain/      reasoning loop, tool dispatch, context planning,
            provider boundary, memory/activity/situation stores
computer/   platform-independent computer control: observe an interface,
            resolve an element, click, type, verify
tools/      filesystem, terminal, browser, spreadsheet, arithmetic, email,
            system and IDE actions the model can call
ui/         PySide6 interface
voice/      wake word, speech-to-text, text-to-speech
vision/     screen understanding (fallback when the accessibility tree
            cannot answer)
ide/        local HTTP bridge for editor integration
core/       the tool executor shared by the runtime
auth/       Google OAuth for the mail capability
config/     model, context, and user preferences
design/     architecture notes and the evidence behind them
tests/      unit, regression, safety, and real end-to-end suites
vscode-extension/   companion VS Code extension for the bridge above
```

## Running locally

Requires [Ollama](https://ollama.com) running locally with `qwen3.5:9b`
pulled. It needs roughly 7 GB resident at the configured 40,960-token context.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own values — see below
python -m ui.app
```

Mike needs Accessibility permission (System Settings → Privacy & Security →
Accessibility) to observe and operate other applications. Without it the
computer-control tools report that they are unavailable rather than failing
silently.

### Environment variables

Copy `.env.example` to `.env`. None of the values are provided.

- `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` — only needed if you
  wire up a cloud model provider; the default path runs entirely on the local
  Ollama model.
- `APP_NAME`, `DEFAULT_BROWSER`, `WAKE_WORD` — basic app config.

Google API access (for the mail capability under `auth/` and
`tools/email/`) needs its own `credentials.json` from a Google Cloud project —
not included, and not committed.

## Testing

```bash
venv/bin/python -m pytest tests/ -q
```

Tests that drive real applications are excluded by default, because they
contend with whatever else is on screen and fail intermittently for reasons
unrelated to the code. Opt in with:

```bash
MIKE_RUN_APP_E2E=1 venv/bin/python -m pytest tests/ -q
```

The suite cannot send mail. The live send path is severed for every test
unless one explicitly marks itself `sends_real_email`, after an early version
of one test sent ten real messages before it was caught.

`tests/endurance_*.py` are real agent runs against real files, a real browser
and a real mailbox. They are run by hand, take minutes each, and verify
themselves against the resulting state rather than against what the model
said. `tests/benchmark_phase2.py` runs them repeatedly and prints one table.

## Safety

Anything that cannot be undone stops and asks first: writing or deleting a
file, running a command, editing code, changing spreadsheet cells, forgetting
a memory, and sending mail. They pass through one gate in
`brain/core_tools.py`, not a per-feature check.

Clicking is gated by what is being clicked rather than by the fact that it is
a click — a control labelled Send, Delete, Pay or Publish stops for the user
in whatever application it lives in, so Mike can navigate and prepare freely
while the irreversible step still waits. Confirmations are built by reading
real state (the cells that will change, the memories that will go, the file
that will be attached), never by restating the model's own description.

## Status

Early / actively developed. Expect breaking changes.
