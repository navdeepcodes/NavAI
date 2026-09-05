"""A long, real agentic task — the kind of work Mike is actually for.

The benchmark tasks are each a few steps. This is one continuous piece of
work with a dependency chain: understand an unfamiliar project, find a bug
across files, fix it, add a feature, and prove both with the project's own
tests. It runs through the real runtime with real tools against real files,
and every claim is checked against disk rather than against what the model
said.

It exists to surface what short tasks cannot: context drift over many turns,
history trimming losing the goal, tool-call reliability across a long run,
and whether Mike's activity record still matches reality at the end.

    venv/bin/python tests/endurance_agentic.py [--model M] [--provider P]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MIKE_DATA_DIR", str(Path.home() / ".mike-brain-lab"))

# Long enough for a real multi-step task on a local model, bounded so a stuck
# run ends rather than hanging the session.
TIME_BUDGET = 1500


def build_project(root: str) -> None:
    """A small project with a genuine cross-file bug and a missing feature.

    The bug is deliberately one that reading a single file cannot reveal:
    `apply_discount` is correct on its own and wrong only in how `total`
    calls it, so the model has to relate two files.
    """
    Path(root, "store").mkdir(parents=True, exist_ok=True)

    Path(root, "store", "pricing.py").write_text(
        "def apply_discount(amount, percent):\n"
        '    """Return amount reduced by percent (0-100)."""\n'
        "    return amount - (amount * percent / 100)\n"
    )
    # The bug: passes a fraction where a percent is expected.
    Path(root, "store", "cart.py").write_text(
        "from store.pricing import apply_discount\n"
        "\n"
        "def total(items, discount_percent=0):\n"
        "    subtotal = sum(i['price'] * i['qty'] for i in items)\n"
        "    return apply_discount(subtotal, discount_percent / 100)\n"
    )
    Path(root, "store", "__init__.py").write_text("")

    Path(root, "test_cart.py").write_text(
        "from store.cart import total\n"
        "\n"
        "ITEMS = [{'price': 100, 'qty': 2}]\n"
        "\n"
        "def test_no_discount():\n"
        "    assert total(ITEMS) == 200\n"
        "\n"
        "def test_ten_percent_off():\n"
        "    assert total(ITEMS, 10) == 180\n"
    )
    Path(root, "README.md").write_text(
        "# store\n\nA tiny shopping cart. Run tests with `pytest -q`.\n"
    )


TASK = (
    "The Python project in {root} has a failing test. "
    "Work out why, fix it, and run the tests again to confirm they all pass. "
    "Then add a function called `item_count` to store/cart.py that returns the "
    "total number of items in a cart (summing the 'qty' of each item), and "
    "check that the file still parses."
)


def verify(root: str) -> list[tuple[str, bool, str]]:
    """Objective checks against disk. None of this reads the model's reply."""
    checks: list[tuple[str, bool, str]] = []

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    checks.append((
        "the project's own tests pass",
        proc.returncode == 0,
        f"pytest exit={proc.returncode}: {(proc.stdout or '').strip()[-120:]}",
    ))

    cart = Path(root, "store", "cart.py")
    source = cart.read_text() if cart.exists() else ""

    checks.append((
        "the discount bug is actually fixed",
        "discount_percent / 100" not in source,
        "cart.py still divides the percent before passing it"
        if "discount_percent / 100" in source else "the faulty conversion is gone",
    ))

    checks.append((
        "item_count was added",
        "def item_count" in source,
        "found" if "def item_count" in source else "no item_count in cart.py",
    ))

    # The feature must work, not merely exist.
    works = False
    detail = "item_count missing"
    if "def item_count" in source:
        probe = subprocess.run(
            [sys.executable, "-c",
             "from store.cart import item_count;"
             "print(item_count([{'price':1,'qty':2},{'price':1,'qty':3}]))"],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        works = probe.returncode == 0 and probe.stdout.strip() == "5"
        detail = (probe.stdout or probe.stderr or "").strip()[:120]
    checks.append(("item_count returns the right answer", works, detail))

    checks.append((
        "cart.py still parses",
        _parses(cart),
        "valid Python" if _parses(cart) else "cart.py no longer parses",
    ))
    return checks


def _parses(path: Path) -> bool:
    import ast
    try:
        ast.parse(path.read_text())
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    from brain.core_runtime import CoreRuntime
    from brain.providers import get_provider

    root = tempfile.mkdtemp(prefix="endurance-")
    build_project(root)

    runtime = CoreRuntime()
    if args.model or args.provider:
        runtime._brain = get_provider(provider=args.provider, model=args.model)
        runtime._capabilities = runtime._brain.capabilities()
    brain = runtime._brain_capabilities().model

    calls: list[dict] = []
    original = runtime._execute_tool

    def recording(name, tool_args):
        result = original(name, tool_args)
        calls.append({
            "tool": name,
            "status": result.get("status", "?") if isinstance(result, dict) else "?",
        })
        return result

    runtime._execute_tool = recording

    print(f"brain: {brain}\nproject: {root}\n")
    started = time.time()
    reply = ""
    stopped = ""
    try:
        for kind, payload in runtime.process_streaming(
            TASK.format(root=root), confirm_callback=lambda d: True
        ):
            if kind == "token":
                reply += payload
            elif kind == "tool_start":
                print(f"  [{len(calls) + 1:2}] {payload[:78]}", flush=True)
            if time.time() - started > TIME_BUDGET:
                stopped = "exceeded the time budget"
                break
    except Exception as exc:
        stopped = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.time() - started)
    results = verify(root)
    passed = sum(1 for _, ok, _ in results if ok)

    print(f"\n--- objective verification ({passed}/{len(results)}) ---")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}\n        {detail}")

    failed_calls = [c for c in calls if c["status"] not in ("success", "command_failed")]
    print(f"\ntool calls: {len(calls)}  failed: {len(failed_calls)}  time: {elapsed}s")
    if stopped:
        print(f"stopped early: {stopped}")
    print(f"model's own summary: {reply.strip()[-220:]!r}")

    out = Path(__file__).parent.parent / "design" / f"endurance_{brain.replace(':', '_')}.json"
    out.write_text(json.dumps({
        "brain": brain, "seconds": elapsed, "tool_calls": calls,
        "verification": [{"check": n, "passed": o, "detail": d} for n, o, d in results],
        "reply": reply[-1000:], "stopped_early": stopped,
    }, indent=2))
    print(f"evidence: {out}")


if __name__ == "__main__":
    main()
