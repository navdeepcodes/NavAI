# Mike

A local-first desktop AI assistant for macOS — runs on-device, listens for a
wake word, sees the screen when asked, and can act: read/write files, run
commands, open apps, search the web, and drive an editor through a bridge.
Everything stays on the machine; no cloud model calls.

## Stack

- Python + [PySide6](https://doc.qt.io/qtforpython/) (native Qt UI, custom
  `QPainter` rendering — no Electron)
- [Ollama](https://ollama.com), running `qwen3:8b` locally, for reasoning and
  tool-calling
- macOS-native audio/speech (`say`, `SFSpeechRecognizer` / `NSSpeechRecognizer`,
  Carbon global hotkeys) — no cloud TTS/STT
- SQLite for memory, activity, and situation state

## Structure

```
brain/      core reasoning loop, tool dispatch, memory/activity/situation stores
tools/      filesystem, terminal, browser, system, IDE actions the model can call
ui/         PySide6 interface
voice/      wake word, speech-to-text, text-to-speech
vision/     screen understanding
ide/        local HTTP bridge for editor integration
vscode-extension/   companion VS Code extension for the bridge above
tests/
```

## Running locally

Requires [Ollama](https://ollama.com) running locally with `qwen3:8b` pulled.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own values — see below
python -m ui.app
```

### Environment variables

Copy `.env.example` to `.env`. None of the values are provided.

- `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` — only needed if you
  wire up a cloud model provider; the default path runs entirely on the local
  Ollama model.
- `APP_NAME`, `DEFAULT_BROWSER`, `WAKE_WORD` — basic app config.

Google API access (for anything under `auth/`) needs its own
`credentials.json` from a Google Cloud project — not included, and not
committed.

## Safety

Actions that write, delete, run commands, or edit files always ask for
confirmation first — there's a single gate all of those pass through
(`brain/core_tools.py`), not a per-feature check.

## Status

Early / actively developed. Expect breaking changes.
