"""Real repository test: understand, modify, run, debug and verify an
unfamiliar third-party codebase.

Every previous endurance test handed Mike an empty directory, where anything
it produced was by definition its own. This one is the harder and far more
representative case: 4,600 lines of somebody else's code, with a real bug in
it, and no hint about where.

The subject is bottlepy/bottle checked out at 3d0ace4 — the genuine upstream
state immediately before commit da7e372, "fix: Anonymous route wildcards with
filter" (upstream issue #1505, fixed January 2026). The bug is therefore real
project history, not something invented for the test. Anonymous wildcards
carrying a filter register their input filter under a key like `anon0` while
compiling the pattern as non-capturing, so the key is never produced at match
time and routing dies with KeyError: 'anon0' -> HTTP 500.

Two things make the result trustworthy:

  * The maintainer's own regression test for this bug is HELD OUT. It lives in
    tests/fixtures/, never inside the repository Mike works on, and is applied
    to a throwaway copy only after the run. Mike cannot read it, so it cannot
    fit to it.

  * The repository's later history is pruned, so the actual fix commit is not
    merely unchecked-out but absent from the object store. `git log` is a real
    research tool here and still cannot leak the answer.

Mike is told the symptom in a user's words. It is told no file name, no
function, no line, and no command.

    venv/bin/python tests/endurance_repo.py [--provider P] [--model M]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

REPO = Path.home() / "mike-repo-task" / "bottle"
HELD_OUT = Path(__file__).parent / "fixtures" / "heldout_test_router.py"

# Harder than the greenfield task: an unfamiliar 4,600-line file has to be
# navigated before a single line can be changed. Bounded so a stuck run ends.
TIME_BUDGET = 3000

TASK = """The bottle web framework is checked out at {root}. I'm using it for a small service and I've hit a problem.

When I define a route with an anonymous wildcard that has a filter -- for example @app.route('/item/<:int>') -- and then request /item/5, I get a 500 Internal Server Error instead of my handler running. If I give the wildcard a name instead, like '/item/<n:int>', the same thing works fine.

Please:
- Get oriented in the project first so you understand how it's laid out.
- Reproduce the problem so you can see it happen yourself.
- Work out the actual cause in the framework's own code.
- Fix it.
- Run the project's existing test suite and make sure you haven't broken anything else.
- Start the server and confirm over HTTP that such a route now works.
- Leave the repository in a working state.

Do not edit the project's tests to make things pass."""


class Trajectory:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.llm_turns = 0
        self.parse_failures = 0
        self.retries = 0
        self.truncations = 0
        self.context_events: list[str] = []
        self.history_trims = 0
        self.reply = ""
        self.stopped = ""

    @property
    def commands(self) -> list[str]:
        return [c["args"].get("command", "") for c in self.calls
                if c["tool"] in ("run_command", "run_background")]

    def tools_used(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for call in self.calls:
            counts[call["tool"]] = counts.get(call["tool"], 0) + 1
        return counts

    def repeated_itself(self) -> bool:
        sigs = [f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)}" for c in self.calls]
        return any(len(set(sigs[i:i + 3])) == 1 for i in range(max(0, len(sigs) - 2)))


class LogWatcher:
    def __init__(self) -> None:
        self.path = Path("logs/mike.log")
        self.start = self.path.stat().st_size if self.path.exists() else 0

    def since(self) -> str:
        if not self.path.exists():
            return ""
        with open(self.path, errors="replace") as handle:
            handle.seek(self.start)
            return handle.read()


# == independent verification ==============================================
# None of this reads Mike's reply. All of it runs against the repository on
# disk after the agent has stopped.

PY = str(REPO / "build" / "venv" / "bin" / "python")


def _run(cmd, cwd, timeout=180):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)


def verify() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    py = PY if Path(PY).exists() else sys.executable

    # 1. bottle.py must still be valid Python.
    parses = _run([py, "-c", "import ast,pathlib;ast.parse(pathlib.Path('bottle.py').read_text())"], REPO)
    checks.append(("bottle.py still parses", parses.returncode == 0,
                   (parses.stderr or "valid Python").strip()[-160:]))

    # 2. The bug itself, at the router level.
    probe = _run([py, "-c", (
        "import sys;sys.path.insert(0,'.');import bottle;"
        "app=bottle.Bottle();"
        "app.route('/anonfilter/<:int>')(lambda: 'ok');"
        "app.route('/named/<n:int>')(lambda n: 'ok');"
        "r,a=app.router.match({'PATH_INFO':'/anonfilter/5','REQUEST_METHOD':'GET'});"
        "print('ANON_ARGS=%r' % (a,))"
    )], REPO)
    out = (probe.stdout or "") + (probe.stderr or "")
    anon_ok = probe.returncode == 0 and "ANON_ARGS={}" in out.replace(" ", "")
    checks.append(("anonymous filtered wildcard routes without error", anon_ok,
                   out.strip().splitlines()[-1][:160] if out.strip() else "no output"))

    # Run in its own process: a crash in the anon probe must not be able to
    # masquerade as a regression in named wildcards.
    named = _run([py, "-c", (
        "import sys;sys.path.insert(0,'.');import bottle;"
        "app=bottle.Bottle();"
        "app.route('/named/<n:int>')(lambda n: 'ok');"
        "r,a=app.router.match({'PATH_INFO':'/named/7','REQUEST_METHOD':'GET'});"
        "print('NAMED_ARGS=%r' % (a,))"
    )], REPO)
    nout = (named.stdout or "") + (named.stderr or "")
    named_ok = "NAMED_ARGS={'n':7}" in nout.replace(" ", "")
    checks.append(("named wildcards still pass their value", named_ok,
                   "named route unaffected" if named_ok else nout.strip()[-160:]))

    # 3. The subtle half of the upstream fix: the filter must STILL apply.
    #    A fix that merely stops the crash by dropping the filter is wrong.
    filt = _run([py, "-c", (
        "import sys;sys.path.insert(0,'.');import bottle;"
        "app=bottle.Bottle();"
        "app.route('/anonfilter/<:int>')(lambda: 'ok');"
        "\ntry:\n"
        "    app.router.match({'PATH_INFO':'/anonfilter/notanint','REQUEST_METHOD':'GET'})\n"
        "    print('MATCHED')\n"
        "except bottle.HTTPError as e:\n"
        "    print('REJECTED', e.status_code)\n"
        "except Exception as e:\n"
        "    print('OTHER', type(e).__name__, e)\n"
    )], REPO)
    fout = (filt.stdout or "") + (filt.stderr or "")
    filter_ok = "REJECTED" in fout
    checks.append(("the int filter is still enforced (not dropped)", filter_ok,
                   fout.strip()[-160:] or "no output"))

    # 4. The project's own existing suite, unchanged, must still pass.
    #    Scoped to test/ deliberately. The agent may drop its own reproduction
    #    script in the repo root, and a bare `pytest -q` would collect that too
    #    -- a repro asserting the *broken* behaviour would then fail once the
    #    bug is fixed and be misread as the agent breaking the project. This
    #    check exists to measure the 357 maintainer tests, so it runs those.
    suite = _run([py, "-m", "pytest", "-q", "test/"], REPO, timeout=600)
    tail = (suite.stdout or "").strip().splitlines()
    summary = tail[-1][:160] if tail else (suite.stderr or "")[-160:]
    checks.append(("the project's own test suite passes", suite.returncode == 0, summary))

    # 5. The held-out maintainer regression test. Mike never saw this.
    held = "held-out fixture missing"
    held_ok = False
    if HELD_OUT.exists():
        tmp = Path(tempfile.mkdtemp(prefix="heldout-"))
        copy = tmp / "bottle"
        try:
            shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(
                ".git", "build", "__pycache__", "*.pyc", ".pytest_cache"))
            shutil.copy(HELD_OUT, copy / "test" / "test_router.py")
            run = _run([py, "-m", "pytest", "-q",
                        "test/test_router.py::TestRouter::testAnonWildcard"],
                       copy, timeout=300)
            held_ok = run.returncode == 0
            lines = (run.stdout or "").strip().splitlines()
            held = lines[-1][:160] if lines else (run.stderr or "")[-160:]
        except Exception as exc:
            held = f"{type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    checks.append(("held-out upstream regression test passes", held_ok, held))

    # 6. Integrity: the fix must not have come from weakening the tests.
    diff = _run(["git", "diff", "--stat", "--", "test/"], REPO)
    tests_untouched = not (diff.stdout or "").strip()
    checks.append(("project tests were not modified", tests_untouched,
                   "test/ is unchanged" if tests_untouched
                   else (diff.stdout or "").strip()[:200]))

    # 7. It has to work over real HTTP, not just in-process.
    served, detail = _serves_over_http(py)
    checks.append(("the fixed route works over real HTTP", served, detail))

    return checks


def leftovers() -> list[str]:
    """Untracked files the agent created. Reported, not scored -- a scratch
    reproduction script is untidy, not a failure."""
    out = _run(["git", "status", "--porcelain", "--untracked-files=all"], REPO)
    return [line[3:] for line in (out.stdout or "").splitlines()
            if line.startswith("??") and "build/" not in line]


def _serves_over_http(py: str) -> tuple[bool, str]:
    """Start a real server using the repo's bottle and request the route."""
    port = 8931
    app_dir = Path(tempfile.mkdtemp(prefix="bottleapp-"))
    (app_dir / "app.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "import bottle\n"
        "app = bottle.Bottle()\n"
        "@app.route('/item/<:int>')\n"
        "def item():\n"
        "    return 'anon route reached'\n"
        f"bottle.run(app, host='127.0.0.1', port={port}, quiet=True)\n"
    )
    proc = subprocess.Popen([py, str(app_dir / "app.py")],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        import urllib.error
        import urllib.request
        deadline = time.time() + 20
        last = "server never came up"
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/item/5", timeout=3) as r:
                    body = r.read().decode(errors="replace")
                    return (r.status == 200 and "anon route reached" in body,
                            f"GET /item/5 -> HTTP {r.status}, body={body[:60]!r}")
            except urllib.error.HTTPError as e:
                last = f"GET /item/5 -> HTTP {e.code}"
                break
            except Exception:
                time.sleep(0.4)
        return False, last
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(app_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    if not REPO.exists():
        sys.exit(f"repository not staged at {REPO}")

    from brain.core_runtime import CoreRuntime
    from brain.providers import get_provider

    # Record the pristine state so the diff at the end is meaningful.
    before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                            capture_output=True, text=True).stdout.strip()

    runtime = CoreRuntime()
    if args.model or args.provider:
        runtime._brain = get_provider(provider=args.provider, model=args.model)
        runtime._capabilities = runtime._brain.capabilities()
    brain = runtime._brain_capabilities().model

    traj = Trajectory()
    watcher = LogWatcher()

    original_execute = runtime._execute_tool

    def recording_execute(name, tool_args):
        started = time.time()
        result = original_execute(name, tool_args)
        traj.calls.append({
            "n": len(traj.calls) + 1,
            "tool": name,
            "args": {k: str(v)[:140] for k, v in (tool_args or {}).items()},
            "status": result.get("status", "?") if isinstance(result, dict) else "?",
            "ms": round((time.time() - started) * 1000),
        })
        return result

    runtime._execute_tool = recording_execute

    original_loop = runtime._streaming_loop

    def counting_loop(cb, ce, depth=0):
        traj.llm_turns += 1
        yield from original_loop(cb, ce, depth)

    runtime._streaming_loop = counting_loop

    print(f"brain    : {brain}")
    print(f"repo     : {REPO} @ {before[:8]}")
    print(f"task     : symptom only -- no file, function, line or command given\n")

    started = time.time()
    try:
        for kind, payload in runtime.process_streaming(
            TASK.format(root=REPO), confirm_callback=lambda d: True
        ):
            if kind == "token":
                traj.reply += payload
            elif kind == "tool_start":
                print(f"  [{len(traj.calls) + 1:2}] {payload[:78]}", flush=True)
            if time.time() - started > TIME_BUDGET:
                traj.stopped = "exceeded the time budget"
                break
    except Exception as exc:
        traj.stopped = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.time() - started)

    log = watcher.since()
    traj.parse_failures = log.count("couldn't parse")
    traj.retries = log.count("Retrying after a recoverable model error")
    # Both providers now report truncation with the same wording, so one
    # count covers local and cloud. It previously counted "generation cap",
    # which only ever matched the Ollama message.
    traj.truncations = log.count("generation limit")
    # Two distinct prefixes: "Context pressure:" is tool-count reduction,
    # "Context plan: dropped ..." is history trimming. Counting only the
    # first reported zero while history was actually being dropped.
    traj.context_events = re.findall(
        r"Context (?:pressure|plan): [^\n]+", log)[:20]
    traj.history_trims = len(re.findall(
        r"Context plan: dropped \d+ older message", log))

    print("\nverifying against the repository on disk...", flush=True)
    results = verify()
    passed = sum(1 for _, ok, _ in results if ok)

    diff = subprocess.run(["git", "diff", "--stat"], cwd=str(REPO),
                          capture_output=True, text=True).stdout.strip()

    print(f"\n{'=' * 64}\nTRAJECTORY")
    print(f"  llm turns (steps) : {traj.llm_turns}")
    print(f"  tool calls        : {len(traj.calls)}")
    print(f"  tools used        : {traj.tools_used()}")
    print(f"  commands run      : {len(traj.commands)}")
    print(f"  parse failures    : {traj.parse_failures}")
    print(f"  retries           : {traj.retries}")
    print(f"  gen truncations   : {traj.truncations}")
    print(f"  context events    : {len(traj.context_events)} "
          f"({traj.history_trims} history trim(s))")
    print(f"  repeated itself   : {traj.repeated_itself()}")
    print(f"  elapsed           : {elapsed}s")
    if traj.stopped:
        print(f"  stopped early     : {traj.stopped}")

    print(f"\nCHANGES MADE TO THE REPOSITORY\n{diff or '  (none)'}")
    extra = leftovers()
    if extra:
        print("  untracked files left behind: " + ", ".join(extra[:10]))

    print(f"\nINDEPENDENT VERIFICATION ({passed}/{len(results)})")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")

    print(f"\nMODEL'S OWN CLAIM (not evidence):\n  {traj.reply.strip()[-400:]!r}")

    out = (Path(__file__).parent.parent / "design"
           / f"endurance_repo_{brain.replace(':', '_')}.json")
    out.write_text(json.dumps({
        "brain": brain, "seconds": elapsed, "repo": str(REPO), "base_commit": before,
        "llm_turns": traj.llm_turns, "tool_calls": traj.calls,
        "commands": traj.commands, "parse_failures": traj.parse_failures,
        "retries": traj.retries, "generation_truncations": traj.truncations,
        "context_events": traj.context_events,
        "history_trims": traj.history_trims, "repeated": traj.repeated_itself(),
        "stopped_early": traj.stopped, "diff_stat": diff,
        "verification": [{"check": n, "passed": o, "detail": d} for n, o, d in results],
        "reply": traj.reply[-2000:],
    }, indent=2))
    print(f"\nevidence: {out}")


if __name__ == "__main__":
    main()
