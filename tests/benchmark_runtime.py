"""Mike Computer + Project Runtime V1 — benchmark suite.

The point of this file is one distinction:

    "the model said it completed the task"   (claimed)
              vs
    "the task was objectively completed"     (verified)

Every task ships with a `verify` function that inspects real state — files on
disk, their contents, process liveness, git output — and never reads the
model's reply. A task passes only if verify() says so. The model's own
summary is recorded separately, precisely so the two can disagree and that
disagreement is visible.

This is a benchmark, not a unit test: it runs the real CoreRuntime against
the real local model, so it is slow and its results depend on the model. A
failure here can mean the runtime is inadequate OR the model is — the report
distinguishes those, because they call for different fixes.

Run:  venv/bin/python tests/benchmark_runtime.py [task_id ...]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401 — never touch real user state

# Auto-approve confirmation prompts. The gate is exercised for real (every
# gated call still routes through it and is recorded); this only supplies the
# "yes" a human would click, so an unattended benchmark can proceed.
APPROVE_ALL = True

MAX_SECONDS_PER_TASK = 260


class Recorder:
    """Captures what actually happened during a task, for the report."""

    def __init__(self) -> None:
        self.tool_calls: list[dict] = []
        self.confirmations: list[str] = []
        self.reply = ""
        self.error = ""

    def confirm(self, description: str) -> bool:
        self.confirmations.append(description)
        return APPROVE_ALL


def run_task(task: dict, model: str | None = None, provider: str | None = None) -> dict:
    """Executes one benchmark task end-to-end through the real runtime.

    `model` swaps only the brain — Mike's tools, safety gates, memory and
    context planning are identical for every model, which is what makes two
    runs comparable.
    """
    from brain.core_runtime import CoreRuntime

    workdir = tempfile.mkdtemp(prefix=f"bench-{task['id']}-")
    setup_info = {}
    if task.get("setup"):
        setup_info = task["setup"](workdir) or {}

    rt = CoreRuntime()
    if model or provider:
        # Swap only the brain. Tools, safety gates, memory, projects and
        # context planning are identical for every model — that is what makes
        # two runs comparable.
        from brain.providers import get_provider
        rt._brain = get_provider(provider=provider, model=model)
        rt._capabilities = rt._brain.capabilities()
    rec = Recorder()

    # Patch _execute_tool to record real arguments and real results.
    original = rt._execute_tool

    def recording_execute(function_name, args):
        started = time.monotonic()
        result = original(function_name, args)
        rec.tool_calls.append({
            "tool": function_name,
            "args": _trim_args(args),
            "status": result.get("status", "?"),
            "ms": round((time.monotonic() - started) * 1000),
            "evidence": _evidence(result),
        })
        return result

    rt._execute_tool = recording_execute

    prompt = task["request"].format(workdir=workdir, **setup_info)

    started = time.monotonic()
    try:
        for event, payload in rt.process_streaming(prompt, confirm_callback=rec.confirm):
            if event == "token":
                rec.reply += payload
            if time.monotonic() - started > MAX_SECONDS_PER_TASK:
                rec.error = "exceeded time budget"
                break
    except Exception as exc:
        rec.error = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.monotonic() - started, 1)

    # ── the part that matters: objective verification ──
    # The model's own words are passed through only for tasks whose
    # deliverable *is* an explanation; everything else is checked against real
    # disk and process state and ignores what the model claimed.
    setup_info["_reply"] = rec.reply
    try:
        verified, evidence = task["verify"](workdir, setup_info)
    except Exception as exc:
        verified, evidence = False, f"verifier raised: {type(exc).__name__}: {exc}"

    claimed = _claims_success(rec.reply)

    result = {
        "id": task["id"],
        "name": task["name"],
        "request": prompt,
        "seconds": elapsed,
        "tool_calls": rec.tool_calls,
        "tools_used": sorted({c["tool"] for c in rec.tool_calls}),
        "confirmations": len(rec.confirmations),
        "reply": rec.reply.strip()[-600:],
        "error": rec.error,
        "claimed_success": claimed,
        "verified_success": verified,
        "verification": evidence,
        "workdir": workdir,
        "model": rt._brain_capabilities().model,
    }

    if task.get("cleanup"):
        try:
            task["cleanup"](workdir, setup_info)
        except Exception:
            pass

    return result


def _trim_args(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        s = str(v)
        out[k] = s if len(s) <= 160 else s[:160] + "…"
    return out


def _evidence(result: dict) -> str:
    """A short, factual trace of what the tool returned — the observation the
    model actually got back."""
    if not isinstance(result, dict):
        return str(result)[:200]
    for key in ("exit_code", "replacements", "match_count", "total_lines", "pid"):
        if key in result:
            return f"{key}={result[key]}"
    if result.get("status") == "error":
        return f"error: {str(result.get('error'))[:160]}"
    return str(result.get("result", ""))[:160]


_SUCCESS_HINTS = ("done", "created", "fixed", "added", "updated", "works",
                  "started", "complete", "finished", "here's", "i've", "successfully")


def _claims_success(reply: str) -> bool:
    low = reply.lower()
    if not low.strip():
        return False
    failure_markers = ("i couldn't", "i was unable", "failed to", "i cannot", "unable to")
    if any(m in low for m in failure_markers):
        return False
    return any(h in low for h in _SUCCESS_HINTS)


# ============================================================
# Tasks
# ============================================================

def _write(root: str, rel: str, text: str) -> None:
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ── 1. Inspect an unfamiliar repository ────────────────────

def setup_repo(workdir):
    _write(workdir, "package.json", json.dumps({
        "name": "inventory-api", "version": "2.1.0",
        "scripts": {"test": "jest", "start": "node server.js"},
        "dependencies": {"express": "^4.18.0", "pg": "^8.11.0"},
    }, indent=2))
    _write(workdir, "server.js", "const express = require('express');\n")
    _write(workdir, "src/routes/items.js", "// item routes\n")
    subprocess.run(["git", "init", "-q"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t",
                    "commit", "-qm", "initial commit"], cwd=workdir, capture_output=True)
    return {}


_INSPECT_FACTS = ["inventory-api", "express", "jest"]


def _verify_inspection(info):
    reply = (info.get("_reply") or "").lower()
    found = [f for f in _INSPECT_FACTS if f.lower() in reply]
    return len(found) >= 2, f"repo-specific facts in answer: {found} of {_INSPECT_FACTS}"


def verify_repo(workdir, info):
    """Objective: did it actually inspect, and does the answer contain the
    facts only inspection could supply?"""
    return None, "manual"  # replaced below by inspect_verifier


def make_inspect_verifier(required_facts):
    def verify(workdir, info):
        # This one is judged on the reply, since the deliverable IS the
        # explanation — but only against facts that exist solely in the repo,
        # so a generic answer cannot pass.
        reply = info.get("_reply", "").lower()
        found = [f for f in required_facts if f.lower() in reply]
        ok = len(found) >= max(2, len(required_facts) - 1)
        return ok, f"found {len(found)}/{len(required_facts)} repo-specific facts: {found}"
    return verify


# ── 2. Find and fix a bug ──────────────────────────────────

def setup_bug(workdir):
    _write(workdir, "calc.py", (
        "def add(a, b):\n"
        "    return a - b\n"
        "\n"
        "def multiply(a, b):\n"
        "    return a * b\n"
    ))
    _write(workdir, "test_calc.py", (
        "from calc import add, multiply\n"
        "\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "\n"
        "def test_multiply():\n"
        "    assert multiply(2, 3) == 6\n"
    ))
    return {}


def verify_bug(workdir, info):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=workdir, capture_output=True, text=True, timeout=90,
    )
    passed = proc.returncode == 0
    src = (Path(workdir) / "calc.py").read_text()
    return passed, (
        f"pytest exit={proc.returncode}; calc.py add() body="
        f"{src.splitlines()[1].strip() if len(src.splitlines()) > 1 else '?'}"
    )


# ── 3. Run tests and respond to failures ───────────────────

def setup_failing_tests(workdir):
    _write(workdir, "strutil.py", (
        "def slugify(text):\n"
        "    return text.lower().replace(' ', '-')\n"
        "\n"
        "def titlecase(text):\n"
        "    return text.lower()\n"
    ))
    _write(workdir, "test_strutil.py", (
        "from strutil import slugify, titlecase\n"
        "\n"
        "def test_slugify():\n"
        "    assert slugify('Hello World') == 'hello-world'\n"
        "\n"
        "def test_titlecase():\n"
        "    assert titlecase('hello world') == 'Hello World'\n"
    ))
    return {}


def verify_failing_tests(workdir, info):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=workdir, capture_output=True, text=True, timeout=90,
    )
    return proc.returncode == 0, f"pytest exit={proc.returncode}: {proc.stdout.strip()[-200:]}"


# ── 4. Modify multiple files consistently ──────────────────

def setup_rename(workdir):
    _write(workdir, "db.py", "def get_conn():\n    return 'conn'\n")
    _write(workdir, "api.py", "from db import get_conn\n\ndef handler():\n    return get_conn()\n")
    _write(workdir, "worker.py", "from db import get_conn\n\ndef job():\n    return get_conn()\n")
    return {}


def verify_rename(workdir, info):
    files = ["db.py", "api.py", "worker.py"]
    texts = {f: (Path(workdir) / f).read_text() for f in files}
    all_renamed = all("open_connection" in t for t in texts.values())
    none_stale = not any("get_conn" in t for t in texts.values())
    ok = all_renamed and none_stale
    stale = [f for f, t in texts.items() if "get_conn" in t]
    return ok, f"renamed_in_all={all_renamed}; files_still_stale={stale}"


# ── 5. Diagnose a failing build ────────────────────────────

def setup_broken_build(workdir):
    _write(workdir, "build.sh", "#!/bin/sh\nset -e\npython3 -c 'import json; json.loads(open(\"config.json\").read())'\necho BUILD_OK\n")
    _write(workdir, "config.json", '{"name": "demo", "port": 8080,}')  # trailing comma
    os.chmod(Path(workdir) / "build.sh", 0o755)
    return {}


def verify_broken_build(workdir, info):
    proc = subprocess.run(["sh", "build.sh"], cwd=workdir, capture_output=True, text=True, timeout=60)
    ok = proc.returncode == 0 and "BUILD_OK" in proc.stdout
    try:
        json.loads((Path(workdir) / "config.json").read_text())
        valid = True
    except Exception:
        valid = False
    return ok and valid, f"build exit={proc.returncode}, config_json_valid={valid}"


# ── 6. Start a dev server and verify it ────────────────────

def setup_server(workdir):
    _write(workdir, "serve.py", (
        "import http.server, socketserver\n"
        "PORT = 8765\n"
        "class H(http.server.SimpleHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.send_header('Content-type','text/html')\n"
        "        self.end_headers()\n"
        "        self.wfile.write(b'<h1>Inventory</h1>')\n"
        "with socketserver.TCPServer(('', PORT), H) as httpd:\n"
        "    print('serving on', PORT, flush=True)\n"
        "    httpd.serve_forever()\n"
    ))
    return {}


def verify_server(workdir, info):
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765", timeout=5) as r:
            body = r.read().decode()
        return "Inventory" in body, f"HTTP 200, body contains Inventory: {'Inventory' in body}"
    except Exception as exc:
        return False, f"could not reach server: {exc}"


def cleanup_server(workdir, info):
    from tools.terminal import actions
    actions.shutdown_all()
    subprocess.run("pkill -f 'serve.py'", shell=True, capture_output=True)


# ── 7. Build a small website ───────────────────────────────

def verify_website(workdir, info):
    html = list(Path(workdir).rglob("*.html"))
    if not html:
        return False, "no .html file was created"
    text = html[0].read_text().lower()
    has_structure = "<html" in text or "<!doctype" in text
    has_heading = "<h1" in text
    return has_structure and has_heading, (
        f"created {html[0].name} ({len(text)} chars), html={has_structure}, h1={has_heading}"
    )


# ── 8. Recover from a broken command ───────────────────────

def verify_recovery(workdir, info):
    marker = Path(workdir) / "output.txt"
    if not marker.exists():
        return False, "output.txt was never created"
    return "recovered" in marker.read_text().lower(), f"output.txt={marker.read_text()[:80]!r}"


# ── 9. Create, modify, revert ──────────────────────────────

def verify_create_modify(workdir, info):
    target = Path(workdir) / "notes.txt"
    if not target.exists():
        return False, "notes.txt was not created"
    body = target.read_text()
    return "second line" in body.lower() and "first line" in body.lower(), (
        f"notes.txt contents={body[:120]!r}"
    )


# ── 10. General computer task (outside a repo) ─────────────

def setup_general(workdir):
    _write(workdir, "receipts/jan.txt", "coffee 4.50\nbooks 22.00\n")
    _write(workdir, "receipts/feb.txt", "coffee 5.00\ntrain 12.25\n")
    _write(workdir, "receipts/notes.md", "not a receipt\n")
    return {}


def verify_general(workdir, info):
    summary = list(Path(workdir).glob("*.txt")) + list(Path(workdir).glob("*.md"))
    summary = [p for p in summary if p.name not in ("jan.txt", "feb.txt")]
    if not summary:
        return False, "no summary file was created at the top level"
    text = summary[0].read_text()
    mentions = sum(1 for token in ("jan", "feb") if token in text.lower())
    return mentions >= 2, f"{summary[0].name} mentions {mentions}/2 receipt files"


TASKS = [
    {
        "id": "inspect",
        "name": "Inspect an unfamiliar repository and explain its architecture",
        "request": (
            "Take a look at the project in {workdir} and tell me what it is: "
            "what kind of project, what it depends on, and how to run its tests."
        ),
        "setup": setup_repo,
        # Graded on the explanation, since that is the deliverable — but only
        # against facts that exist inside the generated repo, so a generic
        # answer cannot pass. Self-contained rather than patched by main(),
        # which left it as None when the task was run through other entry
        # points and the verifier crashed.
        "verify": lambda wd, info: _verify_inspection(info),
        "reply_facts": ["inventory-api", "express", "jest"],
    },
    {
        "id": "fixbug",
        "name": "Find a bug and fix it",
        "request": (
            "In {workdir} there's calc.py and test_calc.py. Run the tests, find "
            "why they fail, fix the bug, and run them again to confirm."
        ),
        "setup": setup_bug,
        "verify": verify_bug,
    },
    {
        "id": "testfail",
        "name": "Run tests and respond to failures",
        "request": (
            "Run the tests in {workdir} and fix whatever is failing until they all pass."
        ),
        "setup": setup_failing_tests,
        "verify": verify_failing_tests,
    },
    {
        "id": "multifile",
        "name": "Modify multiple files consistently",
        "request": (
            "In {workdir}, rename the function get_conn to open_connection "
            "everywhere it appears, across every file that uses it."
        ),
        "setup": setup_rename,
        "verify": verify_rename,
    },
    {
        "id": "build",
        "name": "Diagnose a failed build",
        "request": (
            "The build in {workdir} is failing. Run ./build.sh, work out why, "
            "fix it, and run it again to confirm it prints BUILD_OK."
        ),
        "setup": setup_broken_build,
        "verify": verify_broken_build,
    },
    {
        "id": "server",
        "name": "Start a development server and verify it",
        "request": (
            "Start the server in {workdir} by running serve.py in the background, "
            "then check that it actually came up."
        ),
        "setup": setup_server,
        "verify": verify_server,
        "cleanup": cleanup_server,
    },
    {
        "id": "website",
        "name": "Build a small website from a natural-language request",
        "request": (
            "Create a simple one-page website in {workdir} for a coffee shop "
            "called Ember. Give it a heading and a short intro paragraph."
        ),
        "verify": verify_website,
    },
    {
        "id": "recover",
        "name": "Recover from an intentionally broken command",
        "request": (
            "Run this command in {workdir}: 'cat missing_file.txt > output.txt'. "
            "If it fails, work out why and then write the word 'recovered' into "
            "output.txt instead."
        ),
        "verify": verify_recovery,
    },
    {
        "id": "createmodify",
        "name": "Create, then modify a file safely",
        "request": (
            "In {workdir}, create notes.txt containing the line 'first line'. "
            "Then add a second line saying 'second line' without losing the first."
        ),
        "verify": verify_create_modify,
    },
    {
        "id": "general",
        "name": "General computer task outside a code repository",
        "request": (
            "In {workdir} there's a receipts folder. Read the receipt text files "
            "and write a summary file at the top level of {workdir} listing what "
            "each one contains."
        ),
        "setup": setup_general,
        "verify": verify_general,
    },
]


def main() -> None:
    argv = list(sys.argv[1:])
    model = None
    if "--model" in argv:
        i = argv.index("--model")
        model = argv[i + 1]
        del argv[i:i + 2]
    wanted = set(argv)
    tasks = [t for t in TASKS if not wanted or t["id"] in wanted]

    results = []
    for task in tasks:
        print(f"\n{'='*64}\nTASK: {task['name']}\n{'='*64}", flush=True)

        if task["id"] == "inspect":
            facts = task["reply_facts"]
            task = dict(task)
            task["verify"] = lambda wd, info, f=facts: (
                None, "pending"
            )

        result = run_task(task, model=model)

        # The inspect task is graded on its explanation, against facts that
        # exist only inside the generated repo.
        if result["id"] == "inspect":
            reply = result["reply"].lower()
            facts = TASKS[0]["reply_facts"]
            found = [f for f in facts if f.lower() in reply]
            result["verified_success"] = len(found) >= 2
            result["verification"] = f"repo-specific facts in answer: {found} of {facts}"

        results.append(result)

        verdict = "VERIFIED" if result["verified_success"] else "NOT ACHIEVED"
        print(f"\n  claimed : {result['claimed_success']}")
        print(f"  verified: {result['verified_success']}  <- {verdict}")
        print(f"  evidence: {result['verification']}")
        print(f"  tools   : {', '.join(result['tools_used']) or '(none)'}")
        print(f"  calls   : {len(result['tool_calls'])}, confirmations: {result['confirmations']}, {result['seconds']}s")
        if result["error"]:
            print(f"  error   : {result['error']}")

    # Merge with any previous batch so the suite can be run in parts.
    suffix = f"_{model.replace(':', '_')}" if model else ""
    out = Path(__file__).parent.parent / "design" / f"benchmark_results{suffix}.json"
    existing = []
    if out.exists():
        try:
            existing = json.loads(out.read_text())
        except Exception:
            existing = []
    by_id = {r["id"]: r for r in existing}
    for r in results:
        by_id[r["id"]] = r
    merged = [by_id[t["id"]] for t in TASKS if t["id"] in by_id]
    out.write_text(json.dumps(merged, indent=2))

    verified = sum(1 for r in results if r["verified_success"])
    claimed = sum(1 for r in results if r["claimed_success"])
    overclaim = [r["id"] for r in results if r["claimed_success"] and not r["verified_success"]]

    print(f"\n{'='*64}")
    print(f"VERIFIED COMPLETE : {verified}/{len(results)}")
    print(f"CLAIMED COMPLETE  : {claimed}/{len(results)}")
    print(f"OVERCLAIMED       : {len(overclaim)} {overclaim}")
    print(f"\nFull records: {out}")


if __name__ == "__main__":
    main()
