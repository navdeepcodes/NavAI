"""Mike Brain Lab — a bench for comparing brains, not a product surface.

Development tooling. It plugs different brains into the same Mike runtime and
reports what each can actually do, so a choice of model can be made from
evidence rather than from model cards.

    venv/bin/python -m tools.brain_lab list
    venv/bin/python -m tools.brain_lab probe --provider ollama --model qwen3.5:9b
    venv/bin/python -m tools.brain_lab probe --provider deepseek
    venv/bin/python -m tools.brain_lab profile
    venv/bin/python -m tools.brain_lab bench --provider deepseek --tasks fixbug,multifile

Cloud brains cost money, so `probe` is deliberately small and `bench` takes an
explicit task list rather than defaulting to everything.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Never touch real user state from a development bench.
os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

VERDICT_MARK = {
    "reliable": "VERIFIED",
    "supported": "PARTIAL",
    "not_supported": "FAILED",
    "not_tested": "NOT TESTED",
}


def _probe_image() -> str | None:
    """A small rendered screenshot with known content, so a vision answer can
    be checked rather than admired."""
    from PIL import Image, ImageDraw

    path = Path(os.environ["MIKE_DATA_DIR"]) / "probe_screen.png"
    if path.exists():
        return str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (900, 500), "#1e1e1e")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 900, 40], fill="#333333")
    draw.text((15, 14), "main.py - Visual Studio Code", fill="#dddddd")
    draw.text((30, 90), "def calculate_total(items):", fill="#9cdcfe")
    draw.rectangle([20, 200, 880, 260], fill="#5a1d1d")
    draw.text((30, 215), "ERROR: NameError: name 'itms' is not defined", fill="#ff8888")
    draw.text((30, 238), "  at line 42 in checkout.py", fill="#ffaaaa")
    image.save(path)
    return str(path)


def cmd_list(args) -> None:
    from brain.providers import available_providers, get_provider

    print(f"{'provider':12} {'model':34} {'status':12} capabilities")
    print("-" * 96)
    for name in available_providers():
        try:
            brain = get_provider(provider=name)
            caps = brain.capabilities()
            problem = brain.health()
            status = "ready" if problem is None else problem.kind
            have = ",".join(n for n in ("text", "vision", "tools", "streaming") if caps.can(n))
            print(f"{name:12} {caps.model:34} {status:12} {have}")
            if problem is not None:
                print(f"{'':12} └─ {problem.human()[:78]}")
        except Exception as exc:
            print(f"{name:12} {'-':34} {'error':12} {str(exc)[:50]}")


def cmd_probe(args) -> None:
    from brain.capability_probe import probe

    image = None if args.no_vision else _probe_image()
    report = probe(args.provider, args.model, image_path=image)

    print(f"\n=== {report.provider} / {report.model} ===")
    for observation in report.observations:
        mark = VERDICT_MARK.get(observation.verdict, observation.verdict)
        line = f"  {observation.capability:20} {mark:11} {observation.passes}/{observation.trials}"
        if observation.detail:
            line += f"   {observation.detail[:64]}"
        print(line)
    print(f"\n  tokens: in={report.input_tokens} out={report.output_tokens}")


def cmd_profile(args) -> None:
    """What Mike has actually observed, across every brain it has tried."""
    from brain.capability_probe import history

    rows = history()
    if not rows:
        print("No observations recorded yet. Run `probe` first.")
        return

    latest: dict[tuple, dict] = {}
    for row in rows:                       # newest first, so keep the first seen
        latest.setdefault((row["provider"], row["model"], row["capability"]), row)

    brains: dict[tuple, dict] = {}
    for (provider, model, capability), row in latest.items():
        brains.setdefault((provider, model), {})[capability] = row

    for (provider, model), capabilities in sorted(brains.items()):
        print(f"\n{provider} / {model}")
        for capability, row in sorted(capabilities.items()):
            mark = VERDICT_MARK.get(row["verdict"], row["verdict"])
            print(f"  {capability:20} {mark:11} {row['passes']}/{row['trials']}")


def cmd_bench(args) -> None:
    """The existing Mike benchmark, pointed at a chosen brain."""
    from tests.benchmark_runtime import TASKS, run_task

    wanted = set(args.tasks.split(",")) if args.tasks else set()
    tasks = [t for t in TASKS if not wanted or t["id"] in wanted]

    results = []
    for task in tasks:
        print(f"\n=== {task['name']} ===", flush=True)
        result = run_task(task, model=args.model, provider=args.provider)
        results.append(result)
        print(f"  claimed : {result['claimed_success']}")
        print(f"  verified: {result['verified_success']}")
        print(f"  evidence: {result['verification']}")
        print(f"  tools   : {', '.join(result['tools_used']) or '(none)'}")
        print(f"  calls   : {len(result['tool_calls'])}  {result['seconds']}s")

    verified = sum(1 for r in results if r["verified_success"])
    claimed = sum(1 for r in results if r["claimed_success"])
    print(f"\nVERIFIED {verified}/{len(results)}   CLAIMED {claimed}/{len(results)}")

    # Keep the evidence. A benchmark whose reasoning cannot be re-read later
    # is an opinion, not a measurement.
    import json
    label = (args.provider or "ollama") + ("_" + args.model.replace(":", "_") if args.model else "")
    out = Path(__file__).resolve().parent.parent / "design" / f"brainlab_{label}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"evidence: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="brain_lab", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Show configured brains and whether they are reachable")

    probe_parser = sub.add_parser("probe", help="Verify what a brain can actually do")
    probe_parser.add_argument("--provider", default="ollama")
    probe_parser.add_argument("--model", default=None)
    probe_parser.add_argument("--no-vision", action="store_true")

    sub.add_parser("profile", help="Show everything Mike has observed so far")

    bench_parser = sub.add_parser("bench", help="Run the Mike benchmark against a brain")
    bench_parser.add_argument("--provider", default=None)
    bench_parser.add_argument("--model", default=None)
    bench_parser.add_argument("--tasks", default=None, help="Comma-separated task ids")

    args = parser.parse_args()
    {"list": cmd_list, "probe": cmd_probe,
     "profile": cmd_profile, "bench": cmd_bench}[args.command](args)


if __name__ == "__main__":
    main()
