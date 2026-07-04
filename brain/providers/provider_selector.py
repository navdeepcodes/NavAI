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
    Intelligent provider selector.

    Responsibilities
    ----------------
    • Sticky provider reuse
    • Automatic provider scoring
    • Cooldown recovery
    • Automatic failover

    This class does NOT know which provider should be used
    for a task. ProviderPolicy decides that.

    This class simply chooses the healthiest provider from
    the candidate list.
    """

    # =====================================================

    def __init__(
        self,
        registry: ProviderRegistry,
    ) -> None:

        self._registry = registry
        self._current: str | None = None

    # =====================================================
    # Public API
    # =====================================================

    def select(
        self,
        candidates: list[str],
    ) -> BaseLLMProvider:

        self._recover_expired()

        # -------------------------------------------------
        # Prefer current provider if still healthy.
        # Avoid unnecessary switching.
        # -------------------------------------------------

        if self._current is not None:

            try:

                state = self._registry.get(
                    self._current
                )

                if (
                    state.provider.name in candidates
                    and self._usable(state)
                ):

                    logger.debug(
                        "Reusing provider '%s'.",
                        state.provider.name,
                    )

                    return state.provider

            except ValueError:

                self._current = None

        # -------------------------------------------------
        # Score all available providers.
        # -------------------------------------------------

        best_state: ProviderState | None = None
        best_score = float("-inf")

        for name in candidates:

            try:

                state = self._registry.get(name)

            except ValueError:

                continue

            if not self._usable(state):

                continue

            score = self._score(state)

            logger.debug(
                "%s score %.2f",
                state.provider.name,
                score,
            )

            if score > best_score:

                best_score = score
                best_state = state

        if best_state is None:

            raise RuntimeError(
                "No available providers."
            )

        self._current = best_state.provider.name

        logger.info(
            "Selected provider -> %s",
            best_state.provider.name,
        )

        return best_state.provider

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
    ) -> None:

        try:

            state = self._registry.get(
                provider_name
            )

        except ValueError:

            return

        state.mark_failure()

        cooldown = min(
            300 * (2 ** max(0, state.consecutive_failures - 1)),
            3600,
        )

        state.start_cooldown(
            cooldown
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

        self._registry.get(provider_name)

        self._current = provider_name

        logger.info(
            "Forced provider -> %s",
            provider_name,
        )

    # =====================================================
    # Internal
    # =====================================================

    def _recover_expired(
        self,
    ) -> None:

        now = datetime.utcnow()

        for state in self._registry.states():

            if state.status != ProviderStatus.COOLDOWN:
                continue

            if state.cooldown_until is None:
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
        """
        Calculate provider quality.

        Higher score is better.

        Factors
        -------
        • Reliability
        • Historical latency
        • Success rate
        • Consecutive failures

        Capability routing belongs in ProviderPolicy,
        not here.
        """

        score = 100.0

        # ---------------------------------------------
        # Latency
        # Lower latency is better.
        # Maximum penalty: 30.
        # ---------------------------------------------

        if state.average_latency_ms > 0:

            score -= min(
                state.average_latency_ms / 100.0,
                30.0,
            )

        # ---------------------------------------------
        # Historical reliability.
        # Reward providers with successful history.
        # ---------------------------------------------

        score += min(
            state.success_count * 0.10,
            10.0,
        )

        # ---------------------------------------------
        # Success rate.
        # Maximum reward: 25.
        # ---------------------------------------------

        score += (
            state.success_rate * 25.0
        )

        # ---------------------------------------------
        # Consecutive failures.
        # Heavy penalty.
        # ---------------------------------------------

        score -= (
            state.consecutive_failures * 20.0
        )

        # ---------------------------------------------
        # Overall failures.
        # Small penalty.
        # ---------------------------------------------

        score -= min(
            state.failure_count * 0.50,
            10.0,
        )

        return score