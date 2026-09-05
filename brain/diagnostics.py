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
