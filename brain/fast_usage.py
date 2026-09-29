"""How much of today's free Cloudflare allowance Mike has used.

Cloudflare's free Workers AI allowance is 10,000 "neurons" a day, reset at
00:00 UTC. Every response says exactly how many neurons it cost (asked for with
stream_options.include_usage: measured, 27 tokens in and 5 out came back as
0.3818 neurons, the price list to the digit), so this adds them up as they
arrive -- no extra Cloudflare permission, and nothing to guess.

It counts what Mike used. Anything else using the same account (another app,
a dashboard playground) isn't seen here, so it can only under-count; when
Cloudflare itself refuses for lack of allowance, the day is marked used up.

Kept in one small file beside Mike's other local state.
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
import time

from hostplatform import storage
from logs.logger import logger

#: The free allowance, neurons per day. (A paid Cloudflare plan has more; the
#: student who connected one still sees the free figure, which is the one
#: Mike falls back to the local model at.)
DAILY_NEURONS = 10_000
#: Said once a day, in the chat, when this much is used.
WARN_AT = 0.8

_lock = threading.Lock()
_state: dict | None = None


def _path():
    return storage.data_dir() / "fast_usage.json"


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def _blank() -> dict:
    return {"day": _today(), "neurons": 0.0, "calls": 0, "warned": False}


def _load() -> dict:
    """Today's figures, starting a fresh day at 00:00 UTC. Caller holds _lock."""
    global _state
    if _state is None:
        try:
            data = json.loads(_path().read_text(encoding="utf-8"))
            _state = {**_blank(), **data} if isinstance(data, dict) else _blank()
        except (OSError, ValueError):
            _state = _blank()
    if _state.get("day") != _today():
        _state = _blank()
    return _state


def _save() -> None:
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(_state), encoding="utf-8")
    except OSError:
        logger.debug("Couldn't save the Fast mode usage.", exc_info=True)


def record(usage: dict | None) -> None:
    """Add one response's cost. `usage` is the block Cloudflare returns; a
    response without one (an error, an older endpoint) adds nothing."""
    if not isinstance(usage, dict):
        return
    try:
        neurons = float(usage.get("neurons") or 0.0)
    except (TypeError, ValueError):
        return
    if neurons <= 0:
        return
    with _lock:
        state = _load()
        state["neurons"] = float(state["neurons"]) + neurons
        state["calls"] = int(state["calls"]) + 1
        _save()


def mark_used_up() -> None:
    """Cloudflare says the day's allowance is gone: whatever was counted
    here, it's used up -- so the figure never shows room that isn't there."""
    with _lock:
        state = _load()
        if state["neurons"] < DAILY_NEURONS:
            state["neurons"] = float(DAILY_NEURONS)
            _save()


def used() -> float:
    with _lock:
        return float(_load()["neurons"])


def fraction() -> float:
    return min(1.0, used() / DAILY_NEURONS)


def resets_at() -> float:
    """When today's allowance resets (00:00 UTC), as a timestamp."""
    now = _dt.datetime.now(_dt.timezone.utc)
    return (now + _dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()


def _reset_time() -> str:
    return time.strftime("%I:%M %p", time.localtime(resets_at())).lstrip("0")


def describe() -> str:
    """One line for Settings: what's used, and when it resets."""
    used_now = used()
    if used_now >= DAILY_NEURONS:
        return f"Today's free allowance is used up. It resets at {_reset_time()}."
    return (f"Used today: {used_now:,.0f} of {DAILY_NEURONS:,} ({used_now / DAILY_NEURONS:.0%}). "
            f"It resets at {_reset_time()}.")


def warning() -> str | None:
    """A sentence to say once a day, when most of the allowance is gone."""
    with _lock:
        state = _load()
        if state["warned"] or state["neurons"] < DAILY_NEURONS * WARN_AT \
                or state["neurons"] >= DAILY_NEURONS:
            return None
        state["warned"] = True
        _save()
        used_now = float(state["neurons"])
    return (f"You've used {used_now / DAILY_NEURONS:.0%} of today's free Fast mode allowance. "
            f"When it runs out Mike switches to the model on this computer until {_reset_time()}.")


def path_for_erase():
    return _path()
