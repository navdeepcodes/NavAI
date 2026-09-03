/**
 * Mike Bridge — connects VS Code to the local Mike desktop app.
 *
 * Talks to 127.0.0.1 only, over Node's built-in http module, so the extension
 * has no dependencies and no code ever leaves the machine.
 *
 * Out: a context snapshot, pushed when something meaningful changes (debounced).
 * In:  commands, collected by a long poll that Mike holds open until it has work.
 */

const vscode = require('vscode');
const http = require('http');

const HOST = '127.0.0.1';
const DEBOUNCE_MS = 250;
const HEARTBEAT_MS = 15000;
const RETRY_MS = 4000;
const MAX_SELECTION_CHARS = 4000;
const MAX_OPEN_FILES = 40;

let status;
let pushTimer = null;
let polling = false;
let stopped = false;
let connected = false;

// Identifies this window so Mike can tell several open windows apart and
// direct edits at the one the user is actually looking at.
const WINDOW_ID = `w-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

function port() {
  return vscode.workspace.getConfiguration('mike').get('port', 8787);
}

function enabled() {
  return vscode.workspace.getConfiguration('mike').get('enabled', true);
}

function setConnected(value) {
  if (connected === value) return;
  connected = value;
  render();
}

function render() {
  if (!status) return;
  if (!enabled()) {
    status.text = '$(circle-slash) Mike off';
    status.tooltip = 'Mike context sharing is disabled';
  } else if (connected) {
    status.text = '$(pulse) Mike';
    status.tooltip = 'Connected to Mike';
  } else {
    status.text = '$(debug-disconnect) Mike';
    status.tooltip = 'Mike is not running';
  }
  status.show();
}

// ── HTTP helpers ────────────────────────────────────────────

function request(method, path, body, timeoutMs) {
  return new Promise((resolve) => {
    const payload = body ? Buffer.from(JSON.stringify(body)) : null;

    const req = http.request(
      {
        host: HOST,
        port: port(),
        path,
        method,
        headers: payload
          ? { 'Content-Type': 'application/json', 'Content-Length': payload.length }
          : {},
        timeout: timeoutMs,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          let parsed = null;
          if (data) {
            try {
              parsed = JSON.parse(data);
            } catch (_) {
              parsed = null;
            }
          }
          resolve({ ok: true, status: res.statusCode, body: parsed });
        });
      }
    );

    req.on('error', () => resolve({ ok: false }));
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, timedOut: true });
    });

    if (payload) req.write(payload);
    req.end();
  });
}

// ── Context out ─────────────────────────────────────────────

function severityName(severity) {
  switch (severity) {
    case vscode.DiagnosticSeverity.Error:
      return 'error';
    case vscode.DiagnosticSeverity.Warning:
      return 'warning';
    case vscode.DiagnosticSeverity.Information:
      return 'info';
    default:
      return 'hint';
  }
}

function collectDiagnostics(activePath) {
  const out = [];

  for (const [uri, items] of vscode.languages.getDiagnostics()) {
    for (const d of items) {
      // Everything for the file in front of the user; only real errors
      // elsewhere, so Mike isn't handed the whole project's lint output.
      const isActive = uri.fsPath === activePath;
      if (!isActive && d.severity !== vscode.DiagnosticSeverity.Error) continue;

      out.push({
        file: uri.fsPath,
        line: d.range.start.line + 1,
        column: d.range.start.character + 1,
        severity: severityName(d.severity),
        message: d.message,
        source: d.source || '',
      });

      if (out.length >= 50) return out;
    }
  }

  return out;
}

function buildContext() {
  const editor = vscode.window.activeTextEditor;
  const folders = vscode.workspace.workspaceFolders || [];
  const root = folders.length ? folders[0].uri.fsPath : '';

  const context = {
    editorName: 'VS Code',
    windowId: WINDOW_ID,
    focused: vscode.window.state.focused,
    timestamp: Date.now() / 1000,
    workspace: {
      name: vscode.workspace.name || '',
      root,
      folders: folders.map((f) => f.uri.fsPath),
    },
    editor: {},
    cursor: {},
    selection: {},
    openFiles: [],
    diagnostics: [],
  };

  context.openFiles = vscode.workspace.textDocuments
    .filter((d) => !d.isUntitled && d.uri.scheme === 'file')
    .slice(0, MAX_OPEN_FILES)
    .map((d) => d.uri.fsPath);

  if (editor) {
    const doc = editor.document;
    const pos = editor.selection.active;

    context.editor = {
      path: doc.uri.fsPath,
      language: doc.languageId,
      lineCount: doc.lineCount,
      dirty: doc.isDirty,
    };

    context.cursor = { line: pos.line + 1, column: pos.character + 1 };

    if (!editor.selection.isEmpty) {
      let text = doc.getText(editor.selection);
      if (text.length > MAX_SELECTION_CHARS) {
        text = text.slice(0, MAX_SELECTION_CHARS) + '\n…(truncated)';
      }
      context.selection = {
        text,
        startLine: editor.selection.start.line + 1,
        endLine: editor.selection.end.line + 1,
      };
    }

    context.diagnostics = collectDiagnostics(doc.uri.fsPath);
  } else {
    context.diagnostics = collectDiagnostics(null);
  }

  return context;
}

async function pushContext() {
  if (stopped || !enabled()) return;

  const result = await request('POST', '/context', buildContext(), 4000);
  setConnected(result.ok);
}

function schedulePush() {
  if (pushTimer) clearTimeout(pushTimer);
  pushTimer = setTimeout(pushContext, DEBOUNCE_MS);
}

// ── Commands in ─────────────────────────────────────────────

async function runCommand(command) {
  const { action, params } = command;

  try {
    if (action === 'openFile' || action === 'revealLocation') {
      const doc = await vscode.workspace.openTextDocument(params.path);
      const shown = await vscode.window.showTextDocument(doc, { preview: false });

      if (params.line) {
        const line = Math.max(0, Number(params.line) - 1);
        const pos = new vscode.Position(line, 0);
        shown.selection = new vscode.Selection(pos, pos);
        shown.revealRange(
          new vscode.Range(pos, pos),
          vscode.TextEditorRevealType.InCenter
        );
      }

      return { ok: true, path: params.path };
    }

    if (action === 'applyEdit') {
      const doc = await vscode.workspace.openTextDocument(params.path);
      const shown = await vscode.window.showTextDocument(doc, { preview: false });

      const target =
        params.replaceSelection && !shown.selection.isEmpty
          ? shown.selection
          : new vscode.Range(
              doc.positionAt(0),
              doc.positionAt(doc.getText().length)
            );

      const applied = await shown.edit((builder) => {
        builder.replace(target, params.text);
      });

      if (!applied) return { ok: false, error: 'VS Code rejected the edit.' };

      // Persist so anything Mike runs afterwards sees the change on disk.
      await doc.save();

      schedulePush();
      return { ok: true, path: params.path };
    }

    return { ok: false, error: `Unknown action '${action}'.` };
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) };
  }
}

async function pollLoop() {
  if (polling) return;
  polling = true;

  while (!stopped) {
    if (!enabled()) {
      await new Promise((r) => setTimeout(r, RETRY_MS));
      continue;
    }

    // Mike holds this open until it has work or ~20s passes. The window id
    // lets it hand the command to the window the user is actually in.
    const result = await request(
      'GET',
      `/commands?windowId=${encodeURIComponent(WINDOW_ID)}`,
      null,
      30000
    );

    if (!result.ok) {
      setConnected(false);
      await new Promise((r) => setTimeout(r, RETRY_MS));
      continue;
    }

    setConnected(true);

    if (result.status === 200 && result.body && result.body.id) {
      const outcome = await runCommand(result.body);
      await request('POST', '/result', { id: result.body.id, result: outcome }, 5000);
    }
  }

  polling = false;
}

// ── Lifecycle ───────────────────────────────────────────────

function activate(context) {
  stopped = false;

  status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  status.command = 'mike.showStatus';
  context.subscriptions.push(status);
  render();

  context.subscriptions.push(
    vscode.commands.registerCommand('mike.showStatus', () => {
      vscode.window.showInformationMessage(
        connected
          ? `Mike is connected on port ${port()}.`
          : `Mike is not reachable on port ${port()}. Is the app running?`
      );
    })
  );

  // Event-driven rather than polled, so an idle editor costs nothing.
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(schedulePush),
    vscode.window.onDidChangeTextEditorSelection(schedulePush),
    vscode.workspace.onDidChangeWorkspaceFolders(schedulePush),
    vscode.workspace.onDidOpenTextDocument(schedulePush),
    vscode.workspace.onDidCloseTextDocument(schedulePush),
    vscode.workspace.onDidSaveTextDocument(schedulePush),
    vscode.languages.onDidChangeDiagnostics(schedulePush),
    // Focus changes decide which window Mike treats as current.
    vscode.window.onDidChangeWindowState(schedulePush),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('mike')) render();
    })
  );

  // Keeps Mike's view fresh if it starts after VS Code, and doubles as the
  // liveness signal when the user isn't touching anything.
  const heartbeat = setInterval(pushContext, HEARTBEAT_MS);
  context.subscriptions.push({ dispose: () => clearInterval(heartbeat) });

  pushContext();
  pollLoop();
}

function deactivate() {
  stopped = true;
  if (pushTimer) clearTimeout(pushTimer);
}

module.exports = { activate, deactivate };
