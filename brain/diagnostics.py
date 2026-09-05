"""Is Mike's brain actually usable right now, and what can it do?

Reports on the provider and model Mike is genuinely configured to use, asked
through the same boundary the runtime uses. This matters because the previous
version checked one constant while the runtime ran another, so it could
cheerfully report "the model is available" about a model Mike never called.
"""
from __future__ import annotations

from typing import Any

from brain.providers import get_provider
from logs.logger import logger


def check_ollama() -> dict[str, Any]:
    """Kept under its original name because the UI calls it; it now reports on
    whichever brain is configured, not specifically on Ollama."""
    return check_brain()


def check_brain() -> dict[str, Any]:
    """
    Returns the shape the UI already expects — reachable / model_pulled /
    detail — plus the capability information needed to explain a limitation
    in human terms rather than as an API error.
    """
    try:
        brain = get_provider()
        caps = brain.capabilities()
    except Exception as exc:
        logger.exception("Could not construct the configured brain.")
        return {
            "reachable": False,
            "model_pulled": False,
            "provider": "unknown",
            "model": "unknown",
            "detail": f"Mike's brain isn't configured correctly: {exc}",
            "capabilities": {},
        }

    problem = brain.health()

    result: dict[str, Any] = {
        "provider": caps.provider,
        "model": caps.model,
        "capabilities": {
            "text": caps.can("text"),
            "vision": caps.can("vision"),
            "tools": caps.can("tools"),
            "streaming": caps.can("streaming"),
            "context_tokens": caps.context_tokens,
            "max_input_tokens": caps.max_input_tokens,
        },
        "summary": caps.explain(),
    }

    if problem is None:
        result.update({
            "reachable": True,
            "model_pulled": True,
            "detail": f"{caps.model} is available via {caps.provider}.",
        })
        return result

    # "unavailable" covers both "backend is down" and "model isn't installed";
    # the message already distinguishes them for the person reading it.
    result.update({
        "reachable": problem.kind != "unavailable" or "isn't pulled" in problem.message,
        "model_pulled": "isn't pulled" not in problem.message,
        "detail": problem.human(),
    })
    return result


def explain_missing(capability: str) -> str:
    """A plain sentence for when a user asks for something the current brain
    cannot do — 'your model supports text but not vision', not 'API error'."""
    try:
        caps = get_provider().capabilities()
    except Exception:
        return "Mike's brain isn't configured correctly."

    if caps.can(capability):
        return f"{caps.model} does support {capability}."
    return (
        f"{caps.model} doesn't support {capability}. "
        f"{caps.explain()} Switching to a model that does would enable it."
    )


def check_hardware() -> dict[str, Any]:
    """What this machine is, and whether what Mike is running fits on it.

    Reported rather than acted on. Mike does not resize himself behind the
    user's back — the point is that "why is this slow" has an answer that is
    a measurement instead of a guess.
    """
    from brain.hardware import current

    machine = current()
    report = machine.as_dict()
    report["headroom_gb"] = machine.headroom_gb()
    report["under_pressure"] = machine.under_pressure()

    concerns: list[str] = []
    if machine.under_pressure():
        concerns.append(
            f"only {machine.available_memory_gb:.1f} GB of memory is available; "
            "responses will be slow and audio may stutter"
        )
    if machine.free_disk_gb < 5:
        concerns.append(
            f"only {machine.free_disk_gb:.0f} GB of disk is free; "
            "models and logs need room"
        )
    report["concerns"] = concerns
    return report


def check_voice() -> dict[str, Any]:
    """Which voice Mike will actually use, and why — before he needs it.

    The configured voice and the voice that will speak are not always the
    same thing: a missing model or a broken runtime falls back silently and
    on purpose. This is where that becomes visible.
    """
    from voice.providers import get_provider
    from voice.providers.native import NativeVoice

    try:
        from config import preferences

        configured = str(preferences.get("voice_provider", "native"))
    except Exception:
        configured = "native"

    provider = get_provider(configured)
    ok, detail = provider.available()
    report = {
        "configured": configured,
        "will_use": provider.name if ok else NativeVoice().name,
        "available": ok,
        "detail": detail,
    }
    if configured != report["will_use"]:
        report["reason"] = detail
    return report
