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

// What ran in the terminals: the student's own commands and the ones Mike
// started, each with its exit code and the end of what it printed -- so "why
// did that fail?" is answered from the real output, not a guess.
const MAX_RUNS = 8;
const KEPT_OUTPUT = 20000;     // characters of each command's output held here
const SHARED_OUTPUT = 3000;    // the end of it sent with every snapshot
const OUTPUT_PUSH_MS = 2000;   // a chatty server refreshes Mike's view this often
const SHELL_READY_MS = 10000;  // a new Git Bash on a slow laptop takes a few seconds

let status;
let pushTimer = null;
let outputTimer = null;
let polling = false;
let stopped = false;
let connected = false;
let version = '';

const runs = [];                  // newest last, at most MAX_RUNS
const runsById = new Map();       // Mike's runs stay findable while their terminal lives
const runsByExecution = new Map();
let runCount = 0;

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

// ── Terminals ───────────────────────────────────────────────

function canRunCommands() {
  return Boolean(vscode.window.onDidEndTerminalShellExecution);
}

// Terminal output as a person would read it: colour and cursor codes gone,
// and a line redrawn in place (a progress bar) kept only as it finally stood.
function readable(raw) {
  const plain = String(raw || '')
    .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, '')
    .replace(/\x1b\[[0-?]*[ -\/]*[@-~]/g, '')
    .replace(/\x1b[@-Z\\-_]/g, '')
    .replace(/\r\n/g, '\n');
  return plain
    .split('\n')
    .map((line) => line.split('\r').pop())
    .join('\n');
}

function tail(text, limit) {
  const clean = readable(text).trimEnd();
  if (clean.length <= limit) return clean;
  return '…' + clean.slice(clean.length - limit);
}

function describeRun(run, limit) {
  return {
    id: run.id,
    terminal: run.terminal,
    command: run.command,
    cwd: run.cwd,
    running: run.running,
    exitCode: run.exitCode,
    startedAt: run.startedAt,
    endedAt: run.endedAt,
    byMike: run.byMike,
    output: tail(run.raw, limit),
  };
}

function finishRun(run, exitCode) {
  if (!run.running) return;
  run.running = false;
  run.exitCode = typeof exitCode === 'number' ? exitCode : null;
  run.endedAt = Date.now() / 1000;
  run.resolveEnded();
  schedulePush();
}

function scheduleOutputPush() {
  if (outputTimer) return;
  outputTimer = setTimeout(() => {
    outputTimer = null;
    schedulePush();
  }, OUTPUT_PUSH_MS);
}

// One command in one terminal, followed from start to finish. Reading starts
// at once: the stream only carries what's printed after read() is called.
function track(execution, terminal, byMike) {
  const known = runsByExecution.get(execution);
  if (known) {
    if (byMike) known.byMike = true;
    return known;
  }

  const run = {
    id: `r${++runCount}`,
    terminal: terminal.name,
    terminalRef: terminal,
    command: (execution.commandLine && execution.commandLine.value) || '',
    cwd: execution.cwd ? execution.cwd.fsPath : '',
    running: true,
    exitCode: null,
    startedAt: Date.now() / 1000,
    endedAt: 0,
    byMike: Boolean(byMike),
    raw: '',
  };
  run.ended = new Promise((resolve) => (run.resolveEnded = resolve));

  runsByExecution.set(execution, run);
  runsById.set(run.id, run);
  runs.push(run);
  while (runs.length > MAX_RUNS) {
    const old = runs.shift();
    if (!old.byMike || !old.running) runsById.delete(old.id);
  }

  (async () => {
    try {
      for await (const data of execution.read()) {
        run.raw = (run.raw + data).slice(-KEPT_OUTPUT);
        scheduleOutputPush();
      }
    } catch (_) {
      // The terminal went away mid-read; what was read is kept.
    }
  })();

  schedulePush();
  return run;
}

function waitForShell(terminal, timeoutMs) {
  if (terminal.shellIntegration) return Promise.resolve(terminal.shellIntegration);
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      sub.dispose();
      resolve(undefined);
    }, timeoutMs);
    const sub = vscode.window.onDidChangeTerminalShellIntegration((e) => {
      if (e.terminal !== terminal) return;
      clearTimeout(timer);
      sub.dispose();
      resolve(e.shellIntegration);
    });
  });
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

// A terminal of Mike's, started in the same folder, that has finished what
// it ran: the next thing with that name runs there instead of in a new tab
// every restart. (Another folder gets its own terminal -- no `cd` to quote
// for whichever shell it is.)
function idleMikeTerminal(name, cwd) {
  const norm = (p) => String(p || '').replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
  return vscode.window.terminals.find((t) => {
    if (t.name !== name || t.exitStatus) return false;
    const opts = t.creationOptions || {};
    const made = opts.cwd ? (typeof opts.cwd === 'string' ? opts.cwd : opts.cwd.fsPath) : '';
    if (norm(made) !== norm(cwd)) return false;
    const mine = runs.concat([...runsById.values()]).filter((r) => r.terminalRef === t);
    return mine.length > 0 && mine.every((r) => !r.running);
  });
}

async function runInTerminal(params) {
  if (!canRunCommands()) {
    return { ok: false, unsupported: true, error: 'This VS Code is too old to run commands for Mike.' };
  }

  const name = String(params.name || 'Mike').slice(0, 40);
  let terminal = idleMikeTerminal(name, params.cwd || '');
  let fresh = false;
  if (!terminal) {
    const options = { name, cwd: params.cwd || undefined };
    if (params.shellPath) {
      options.shellPath = params.shellPath;
      options.shellArgs = params.shellArgs || [];
    }
    terminal = vscode.window.createTerminal(options);
    fresh = true;
  }
  // Shown without taking the keyboard: the student keeps typing where they were.
  terminal.show(true);

  const shell = await waitForShell(terminal, SHELL_READY_MS);
  if (!shell) {
    if (fresh) terminal.dispose();
    return {
      ok: false,
      noShellIntegration: true,
      error: "VS Code's terminal didn't report back, so Mike can't follow what runs there.",
    };
  }

  const execution = shell.executeCommand(String(params.command || ''));
  const run = track(execution, terminal, true);

  await Promise.race([run.ended, delay(Math.max(0, Number(params.waitMs) || 4000))]);
  let pid = null;
  try {
    pid = await terminal.processId;
  } catch (_) {
    pid = null;
  }
  return { ok: true, pid, ...describeRun(run, 6000) };
}

async function stopRun(params) {
  const run = runsById.get(params.runId);
  if (!run) return { ok: false, error: 'Mike has no record of that command in VS Code.' };
  if (run.running) {
    run.terminalRef.sendText('\x03', false);
    await Promise.race([run.ended, delay(3000)]);
  }
  if (run.running) {
    // Ctrl+C wasn't enough: closing the terminal ends everything in it.
    run.terminalRef.dispose();
    await Promise.race([run.ended, delay(1500)]);
    finishRun(run, null);
  }
  return { ok: true, ...describeRun(run, 3000) };
}

// ── The editor's own checks, for files Mike wrote ───────────

function problemsOf(uri) {
  return vscode.languages
    .getDiagnostics(uri)
    .filter((d) => d.severity <= vscode.DiagnosticSeverity.Warning)
    .slice(0, 20)
    .map(describeDiagnostic);
}

function inTab(uri) {
  const key = uri.toString();
  return vscode.window.tabGroups.all.some((g) =>
    g.tabs.some((t) => t.input && t.input.uri && t.input.uri.toString() === key)
  );
}

// Opens each file as a tab behind the one the student is on -- VS Code's
// checkers only look at files in a tab (measured: a document opened out of
// sight got no report at all, not even for broken JSON) -- and waits until
// each has been checked or the time is up. The tabs stay: they're the files
// Mike just wrote, where the student can look. A file that comes back clean
// usually says nothing at all, so "reported" is only ever a yes.
async function problemsFor(params) {
  const uris = (params.paths || []).map((p) => vscode.Uri.file(String(p)));
  const waitMs = Math.max(0, Number(params.waitMs) || 2000);
  const reported = new Set();
  const sub = vscode.languages.onDidChangeDiagnostics((e) => {
    for (const u of e.uris) reported.add(u.toString());
  });
  try {
    for (const u of uris) {
      if (!inTab(u)) {
        await vscode.commands
          .executeCommand('vscode.open', u, { background: true, preview: false, preserveFocus: true })
          .then(() => null, () => null);
      }
      // A tab behind the active one isn't loaded until someone looks at it,
      // and an unloaded file isn't checked (measured: nothing reported in
      // 15s until the text was loaded). This loads it.
      await vscode.workspace.openTextDocument(u).then(() => null, () => null);
    }
    const deadline = Date.now() + waitMs;
    while (Date.now() < deadline && !uris.every((u) => reported.has(u.toString()))) {
      await delay(100);
    }
    await delay(150);
  } finally {
    sub.dispose();
  }
  return {
    ok: true,
    files: uris.map((u) => ({
      path: u.fsPath,
      reported: reported.has(u.toString()),
      problems: problemsOf(u),
    })),
  };
}

function buildContext() {
  const editor = vscode.window.activeTextEditor;
  const folders = vscode.workspace.workspaceFolders || [];
  const root = folders.length ? folders[0].uri.fsPath : '';

  const context = {
    editorName: 'VS Code',
    extensionVersion: version,
    canRunCommands: canRunCommands(),
    windowId: WINDOW_ID,
    focused: vscode.window.state.focused,
    timestamp: Date.now() / 1000,
    terminal: runs.map((r) => describeRun(r, SHARED_OUTPUT)),
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

function samePath(a, b) {
  if (process.platform !== 'win32') return a === b;
  const norm = (p) => String(p || '').replace(/\//g, '\\').toLowerCase();
  return norm(a) === norm(b);
}

// The open document for a path, if this window has one: its text is the
// truth, unsaved changes included -- the file on disk may be older.
function openDocument(path) {
  return vscode.workspace.textDocuments.find(
    (d) => d.uri.scheme === 'file' && samePath(d.uri.fsPath, path)
  );
}

function describeDiagnostic(d) {
  return {
    line: d.range.start.line + 1,
    column: d.range.start.character + 1,
    severity: severityName(d.severity),
    message: d.message,
    source: d.source || '',
  };
}

// The file's errors and warnings once the language server has looked at an
// edit: resolves on its next report for this file, or after `timeoutMs`
// (a file type with no checker never reports).
function diagnosticsAfter(uri, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    let timer = null;
    let sub = null;
    const finish = () => {
      if (done) return;
      done = true;
      if (sub) sub.dispose();
      if (timer) clearTimeout(timer);
      resolve(
        vscode.languages
          .getDiagnostics(uri)
          .filter((d) => d.severity <= vscode.DiagnosticSeverity.Warning)
          .slice(0, 20)
          .map(describeDiagnostic)
      );
    };
    sub = vscode.languages.onDidChangeDiagnostics((e) => {
      if (e.uris.some((u) => u.toString() === uri.toString())) setTimeout(finish, 150);
    });
    timer = setTimeout(finish, timeoutMs);
  });
}

async function runCommand(command) {
  const { action, params } = command;

  try {
    if (action === 'readText') {
      const doc = openDocument(params.path);
      if (!doc) return { ok: false, open: false };
      return { ok: true, open: true, text: doc.getText(), dirty: doc.isDirty };
    }

    if (action === 'replaceRange') {
      // An edit Mike made against the text he read -- applied only if that
      // text is still there, so a student typing meanwhile never has their
      // work overwritten. It lands in the editor, so Ctrl+Z undoes it.
      const doc = openDocument(params.path);
      if (!doc) return { ok: false, open: false };
      const range = new vscode.Range(
        params.startLine, params.startChar, params.endLine, params.endChar
      );
      const current = doc.getText(range).replace(/\r\n/g, '\n');
      if (current !== params.old) {
        return { ok: false, changed: true, error: 'The file changed in the editor since Mike read it.' };
      }
      const edit = new vscode.WorkspaceEdit();
      edit.replace(doc.uri, range, params.text);
      const problems = diagnosticsAfter(doc.uri, 1500);
      if (!(await vscode.workspace.applyEdit(edit))) {
        return { ok: false, error: 'VS Code rejected the edit.' };
      }
      await doc.save();
      schedulePush();
      return { ok: true, problems: await problems };
    }

    if (action === 'runInTerminal') return await runInTerminal(params);

    if (action === 'runOutput') {
      const run = runsById.get(params.runId);
      if (!run) return { ok: false, error: 'Mike has no record of that command in VS Code.' };
      return { ok: true, ...describeRun(run, Number(params.limit) || 6000) };
    }

    if (action === 'stopRun') return await stopRun(params);

    if (action === 'problems') return await problemsFor(params);

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
  version = (context.extension && context.extension.packageJSON.version) || '';

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
    }),
    // Ask Mike without leaving the editor: he sees the file, the selection
    // and the problems VS Code reports, and answers in his own window.
    vscode.commands.registerCommand('mike.ask', async () => {
      await pushContext();
      const editor = vscode.window.activeTextEditor;
      const selected = editor && !editor.selection.isEmpty;
      const name = editor ? editor.document.fileName.split(/[\\/]/).pop() : '';
      const question = await vscode.window.showInputBox({
        prompt: 'Ask Mike',
        placeHolder: selected
          ? 'About the selected code…'
          : name ? `About ${name}…` : 'Anything about your code…',
        ignoreFocusOut: true,
      });
      if (!question || !question.trim()) return;
      const sent = await request('POST', '/ask', { windowId: WINDOW_ID, question: question.trim() }, 4000);
      if (!sent.ok || sent.status !== 200) {
        vscode.window.showWarningMessage("Mike isn't running. Open Mike and ask again.");
        return;
      }
      vscode.window.setStatusBarMessage('$(pulse) Asked Mike', 3000);
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

  if (canRunCommands()) {
    context.subscriptions.push(
      vscode.window.onDidStartTerminalShellExecution((e) => track(e.execution, e.terminal, false)),
      vscode.window.onDidEndTerminalShellExecution((e) => {
        const run = runsByExecution.get(e.execution);
        if (run) finishRun(run, e.exitCode);
      }),
      vscode.window.onDidCloseTerminal((terminal) => {
        for (const run of runsById.values()) {
          if (run.terminalRef === terminal) {
            finishRun(run, null);
            if (!runs.includes(run)) runsById.delete(run.id);
          }
        }
      })
    );
  }

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
