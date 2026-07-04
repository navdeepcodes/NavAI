from __future__ import annotations

from datetime import datetime

from logs.logger import logger

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.provider_registry import ProviderRegistry
from brain.providers.provider_state import (
    ProviderState,
    ProviderStatus,
)


class ProviderSelector:
    """
    Selects which provider should execute the next request.

    Responsibilities
    ----------------
    • Sticky provider selection
    • Automatic failover
    • Cooldown recovery

    Never
    -----
    • Execute LLM requests
    • Perform health checks
    • Decide provider priorities
    """

    # =====================================================

    def __init__(
        self,
        registry: ProviderRegistry,
    ) -> None:

        self._registry = registry

        self._current: str | None = None

    # =====================================================

    def select(
        self,
        candidates: list[str],
    ) -> BaseLLMProvider:

        self._recover_expired()

        # -----------------------------------------
        # Reuse current provider if possible
        # -----------------------------------------

        if self._current is not None:

            try:

                state = self._registry.get(
                    self._current
                )

                if self._usable(state):

                    logger.debug(
                        "Reusing provider '%s'.",
                        state.provider.name,
                    )

                    return state.provider

            except ValueError:

                self._current = None

        # -----------------------------------------
        # Select first usable provider
        # -----------------------------------------

        for name in candidates:

            try:

                state = self._registry.get(
                    name
                )

            except ValueError:

                continue

            if not self._usable(state):

                continue

            self._current = state.provider.name

            logger.info(
                "Switched provider -> %s",
                state.provider.name,
            )

            return state.provider

        raise RuntimeError(
            "No available providers."
        )

    # =====================================================

    def report_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:

        try:

            state = self._registry.get(
                provider_name
            )

        except ValueError:

            return

        state.mark_success(
            latency_ms
        )

    # =====================================================

    def report_failure(
        self,
        provider_name: str,
        cooldown_seconds: int = 300,
    ) -> None:

        try:

            state = self._registry.get(
                provider_name
            )

        except ValueError:

            return

        state.mark_failure()

        state.start_cooldown(
            cooldown_seconds
        )

        logger.warning(
            "%s entered cooldown.",
            provider_name,
        )

        if self._current == provider_name:

            self._current = None

    # =====================================================

    def release(self) -> None:

        self._current = None

    # =====================================================

    def current(
        self,
    ) -> BaseLLMProvider | None:

        if self._current is None:

            return None

        try:

            return self._registry.get(
                self._current
            ).provider

        except ValueError:

            return None

    # =====================================================

    def current_name(
        self,
    ) -> str | None:

        return self._current

    # =====================================================

    def force(
        self,
        provider_name: str,
    ) -> None:

        self._registry.get(
            provider_name
        )

        self._current = provider_name

        logger.info(
            "Forced provider -> %s",
            provider_name,
        )

    # =====================================================

    def _recover_expired(
        self,
    ) -> None:

        now = datetime.utcnow()

        for state in self._registry.states():

            if (
                state.status
                != ProviderStatus.COOLDOWN
            ):

                continue

            if (
                state.cooldown_until
                is None
            ):

                continue

            if now >= state.cooldown_until:

                state.recover()

                logger.info(
                    "%s recovered from cooldown.",
                    state.provider.name,
                )

    # =====================================================

    @staticmethod
    def _usable(
        state: ProviderState,
    ) -> bool:

        if (
            state.status
            == ProviderStatus.COOLDOWN
        ):

            if (
                state.cooldown_until
                and datetime.utcnow()
                >= state.cooldown_until
            ):

                state.recover()

        return state.available