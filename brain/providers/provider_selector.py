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
    Chooses the healthiest provider from a candidate list.

    Responsibilities
    ----------------
    • Sticky provider reuse
    • Provider scoring
    • Cooldown handling
    • Current provider tracking

    NOTE:
    -----
    This class DOES NOT perform request retries or failover.
    LLMService is responsible for trying the next provider.
    """

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

        # -------------------------------------------------
        # Reuse current provider if still healthy
        # -------------------------------------------------

        if self._current:

            state = self._registry.get(self._current)

            if (
                state is not None
                and state.provider.name in candidates
                and self._usable(state)
            ):

                logger.debug(
                    "Reusing provider '%s'.",
                    state.provider.name,
                )

                return state.provider

        # -------------------------------------------------
        # Pick healthiest provider
        # -------------------------------------------------

        best: ProviderState | None = None
        best_score = float("-inf")

        for name in candidates:

            state = self._registry.get(name)

            if state is None:
                continue

            if not self._usable(state):
                continue

            score = self._score(state)

            logger.debug(
                "%s score %.2f",
                name,
                score,
            )

            if score > best_score:

                best_score = score
                best = state

        if best is None:

            raise RuntimeError(
                "No available providers."
            )

        self._current = best.provider.name

        logger.info(
            "Selected provider -> %s",
            best.provider.name,
        )

        return best.provider

    # =====================================================

    def report_success(
        self,
        provider_name: str,
        latency_ms: float,
    ) -> None:

        state = self._registry.get(provider_name)

        if state is None:
            return

        state.mark_success(latency_ms)

    # =====================================================

    def report_failure(
        self,
        provider_name: str,
    ) -> None:

        state = self._registry.get(provider_name)

        if state is None:
            return

        state.mark_failure()

        cooldown = min(
            60 * (2 ** (state.consecutive_failures - 1)),
            1800,
        )

        state.start_cooldown(
            cooldown,
        )

        logger.warning(
            "%s entered cooldown for %ss.",
            provider_name,
            cooldown,
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

        state = self._registry.get(
            self._current,
        )

        return (
            None
            if state is None
            else state.provider
        )

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

        self._registry.get(provider_name)

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
                state.status == ProviderStatus.COOLDOWN
                and state.cooldown_until
                and now >= state.cooldown_until
            ):

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
            state.status == ProviderStatus.COOLDOWN
            and state.cooldown_until
            and datetime.utcnow() >= state.cooldown_until
        ):

            state.recover()

        return state.available

    # =====================================================

    @staticmethod
    def _score(
        state: ProviderState,
    ) -> float:

        score = 100.0

        if state.average_latency_ms > 0:

            score -= min(
                state.average_latency_ms / 100.0,
                30.0,
            )

        score += min(
            state.success_count * 0.1,
            10.0,
        )

        score += (
            state.success_rate * 25.0
        )

        score -= (
            state.consecutive_failures * 20.0
        )

        score -= min(
            state.failure_count * 0.5,
            10.0,
        )

        return score