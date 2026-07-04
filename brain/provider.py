from __future__ import annotations

from brain.providers.provider_manager import ProviderManager
from brain.providers.provider_selector import ProviderSelector

# ==========================================================
# Singleton Provider System
# ==========================================================

manager = ProviderManager()

selector = ProviderSelector(
    manager.registry,
)


def get_provider(
    *,
    model: str | None = None,
    task: str | None = None,
):
    """
    Compatibility helper for legacy code.

    New code should use:
        ProviderRouter
        LLMService

    Returns the provider selected by the current routing policy.
    """

    # ---------------------------------------------------------
    # Explicit model selection
    # ---------------------------------------------------------

    if model is not None:
        return manager.by_model(model)

    # ---------------------------------------------------------
    # Task routing
    # ---------------------------------------------------------

    if task is None:
        task = "general"

    candidates = manager.policy.providers_for(task)

    return selector.select(candidates)