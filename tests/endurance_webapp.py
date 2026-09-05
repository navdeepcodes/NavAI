"""Real end-to-end agent test: build, run, inspect and improve a web page.

Mike is given one high-level request and nothing else — no file names, no
commands, no stack. Everything about how to do it is the model's decision.
This harness only records what happened and then checks the result against
the filesystem and the running server, never against what the model claimed.

Run it with a browser visible: see_screen captures the whole screen, so the
vision step is only meaningful if the rendered page is actually on it.

    venv/bin/python tests/endurance_webapp.py                # local brain
    venv/bin/python tests/endurance_webapp.py --provider deepseek
    venv/bin/python tests/endurance_webapp.py --keep         # keep the project
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

# Generous: this is a long piece of real work on a local model. Bounded so a
# stuck run ends rather than hanging indefinitely.
TIME_BUDGET = 2400

TASK = """Build a small polished personal landing page for a fictional developer named Alex.

Requirements:
- Use a simple modern web stack that can run locally without external services.
- Create the project from scratch.
- Build the page with:
  - hero section
  - short introduction
  - skills/technology section
  - projects section with 3 fictional projects
  - contact/footer section
- Make it responsive.
- Give it a deliberate visual design rather than a bare HTML page.
- Run it locally.
- Open/inspect the running site in the browser.
- Use screenshots/vision to verify the rendered result.
- Identify at least one thing that could be improved from the actual rendered result.
- Modify the code based on that observation.
- Reload/re-run the site.
- Verify the modification actually appears.
- Run appropriate syntax/build checks.
- Inspect the final files/diff.
- Leave the project in a runnable state.

The project directory is {root}. Work there."""


class Trajectory:
    """Everything that happened, recorded as it happens."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.llm_turns = 0
        self.parse_failures = 0
        self.retries = 0
        self.generation_truncations = 0
        self.context_events: list[str] = []
        self.history_trims = 0
        self.reply = ""
        self.stopped = ""
        self.snapshots: list[dict] = []

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
        """Three identical consecutive calls means it is stuck, not working."""
        signatures = [f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)}" for c in self.calls]
        return any(
            len(set(signatures[i:i + 3])) == 1 for i in range(max(0, len(signatures) - 2))
        )


class LogWatcher:
    """Reads Mike's own log for events the runtime records but does not return."""

    def __init__(self) -> None:
        self.path = Path("logs/mike.log")
        self.start = self.path.stat().st_size if self.path.exists() else 0

    def since(self) -> str:
        if not self.path.exists():
            return ""
        with open(self.path, errors="replace") as handle:
            handle.seek(self.start)
            return handle.read()


def snapshot(root: Path, label: str) -> dict:
    """A screenshot plus the file tree, so evidence survives the run."""
    shots = Path(os.environ["MIKE_DATA_DIR"]) / "endurance_shots"
    shots.mkdir(parents=True, exist_ok=True)
    image = shots / f"{label}.png"
    try:
        subprocess.run(["screencapture", "-x", str(image)], check=True, timeout=30)
        captured = image.exists()
    except Exception:
        captured = False
    return {
        "label": label,
        "screenshot": str(image) if captured else None,
        "files": sorted(str(p.relative_to(root)) for p in root.rglob("*")
                        if p.is_file() and ".git" not in p.parts)[:40],
    }


# ══ independent verification ═══════════════════════════════

SECTIONS = {
    "hero": r"hero|banner|masthead",
    "introduction": r"about|intro|summary",
    "skills": r"skill|tech|stack|tool",
    "projects": r"project|work|portfolio",
    "contact/footer": r"contact|footer|get in touch|email",
}


def verify(root: Path, port_hints: list[int] | None = None) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    html_files = list(root.rglob("*.html"))
    checks.append(("an HTML page exists", bool(html_files),
                   ", ".join(p.name for p in html_files[:5]) or "none found"))
    if not html_files:
        return checks

    page = max(html_files, key=lambda p: p.stat().st_size)
    html = page.read_text(errors="replace")
    css_files = list(root.rglob("*.css"))
    styling = css_files or ("<style" in html.lower())
    combined = html.lower() + "".join(
        p.read_text(errors="replace").lower() for p in css_files[:5]
    )

    checks.append(("styling exists (not a bare page)", bool(styling),
                   f"{len(css_files)} css file(s), inline <style>: {'<style' in html.lower()}"))

    for name, pattern in SECTIONS.items():
        found = re.search(pattern, combined) is not None
        checks.append((f"section: {name}", found, "found" if found else "not detected"))

    projects = len(re.findall(r"project", combined))
    checks.append(("three projects present", projects >= 3,
                   f"{projects} mentions of 'project'"))

    responsive = ("@media" in combined
                  or "viewport" in html.lower()
                  or "grid-template" in combined
                  or "flex" in combined)
    checks.append(("responsive technique used", responsive,
                   f"@media={'@media' in combined}, viewport={'viewport' in html.lower()}"))

    valid_html = html.lower().count("<html") >= 1 and "</html>" in html.lower()
    checks.append(("HTML is structurally complete", valid_html,
                   "has <html> and </html>" if valid_html else "malformed"))

    # Does anything actually serve it?
    served = False
    detail = "no server reachable"
    probes = list(port_hints or []) + [8000, 8080, 3000, 5000, 5173, 8888]
    for port in dict.fromkeys(p for p in probes if p):
        try:
            import requests
            response = requests.get(f"http://127.0.0.1:{port}", timeout=4)
            # A stale server whose directory was deleted and recreated answers
            # 200 with nothing. That is not the site being served.
            if response.status_code == 200 and len(response.text) > 200:
                served = True
                detail = f"port {port} -> HTTP 200, {len(response.text)} bytes"
                break
        except Exception:
            continue
    checks.append(("the site actually serves over HTTP", served, detail))

    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--keep", action="store_true", help="keep the project directory")
    args = parser.parse_args()

    from brain.core_runtime import CoreRuntime
    from brain.providers import get_provider

    root = Path.home() / "mike-endurance-site"
    if root.exists():
        import shutil
        shutil.rmtree(root)
    root.mkdir(parents=True)

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
            "args": {k: (str(v)[:120]) for k, v in (tool_args or {}).items()},
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

    print(f"brain   : {brain}")
    print(f"project : {root}")
    print(f"task    : high-level only — no files or commands specified\n")

    started = time.time()
    seen_server = False
    try:
        for kind, payload in runtime.process_streaming(
            TASK.format(root=root), confirm_callback=lambda d: True
        ):
            if kind == "token":
                traj.reply += payload
            elif kind == "tool_start":
                n = len(traj.calls) + 1
                print(f"  [{n:2}] {payload[:76]}", flush=True)
                # Capture the page the first time something is served.
                if not seen_server and any(
                    t in payload.lower() for t in ("check_url", "checking http", "opening http")
                ):
                    seen_server = True
                    traj.snapshots.append(snapshot(root, "01-initial"))
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
    traj.generation_truncations = log.count("generation limit")
    # Two distinct prefixes: "Context pressure:" is tool-count reduction,
    # "Context plan: dropped ..." is history trimming. Counting only the
    # first reported zero while history was actually being dropped.
    traj.context_events = re.findall(
        r"Context (?:pressure|plan): [^\n]+", log)[:20]
    traj.history_trims = len(re.findall(
        r"Context plan: dropped \d+ older message", log))

    traj.snapshots.append(snapshot(root, "02-final"))

    # Any 4-5 digit number in a command the agent ran is a candidate port.
    # The previous pattern required "port=" or a colon, so a plain
    # `python3 -m http.server 8137` produced no hint at all and verification
    # fell back to a fixed list that did not include the port actually serving
    # the site -- reporting "no server reachable" while the site was up.
    candidates: list[int] = []
    for command in traj.commands:
        for found in re.findall(r"\b(\d{4,5})\b", command):
            port = int(found)
            if 1024 <= port <= 65535 and port not in candidates:
                candidates.append(port)
    results = verify(root, candidates)
    passed = sum(1 for _, ok, _ in results if ok)

    print(f"\n{'='*62}\nTRAJECTORY")
    print(f"  llm turns (steps) : {traj.llm_turns}")
    print(f"  tool calls        : {len(traj.calls)}")
    print(f"  tools used        : {traj.tools_used()}")
    print(f"  commands run      : {len(traj.commands)}")
    print(f"  parse failures    : {traj.parse_failures}")
    print(f"  retries           : {traj.retries}")
    print(f"  gen truncations   : {traj.generation_truncations}")
    print(f"  context events    : {len(traj.context_events)} "
          f"({traj.history_trims} history trim(s))")
    print(f"  repeated itself   : {traj.repeated_itself()}")
    print(f"  elapsed           : {elapsed}s")
    if traj.stopped:
        print(f"  stopped early     : {traj.stopped}")

    print(f"\nINDEPENDENT VERIFICATION ({passed}/{len(results)})")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")

    files = sorted(p for p in root.rglob("*") if p.is_file())
    print(f"\nFILES CREATED ({len(files)})")
    for f in files[:20]:
        print(f"  {f.relative_to(root)}  ({f.stat().st_size} bytes)")

    print(f"\nMODEL'S OWN CLAIM (not evidence):\n  {traj.reply.strip()[-320:]!r}")

    out = Path(__file__).parent.parent / "design" / f"endurance_web_{brain.replace(':','_')}.json"
    out.write_text(json.dumps({
        "brain": brain, "seconds": elapsed, "project": str(root),
        "llm_turns": traj.llm_turns, "tool_calls": traj.calls,
        "commands": traj.commands, "parse_failures": traj.parse_failures,
        "retries": traj.retries, "generation_truncations": traj.generation_truncations,
        "context_events": traj.context_events,
        "history_trims": traj.history_trims, "repeated": traj.repeated_itself(),
        "stopped_early": traj.stopped, "snapshots": traj.snapshots,
        "verification": [{"check": n, "passed": o, "detail": d} for n, o, d in results],
        "reply": traj.reply[-2000:],
    }, indent=2))
    print(f"\nevidence: {out}")
    print(f"project kept at: {root}")


if __name__ == "__main__":
    main()
