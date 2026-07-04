from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from logs.logger import logger

from brain.providers.provider_registry import ProviderRegistry
from brain.providers.provider_state import ProviderStatus


class CooldownManager:
    """
    Manages provider cooldowns.

    Responsibilities
    ----------------
    • Put providers into cooldown
    • Restore providers when cooldown expires
    • Check cooldown state

    Never:
    • Execute requests
    • Perform health checks
    • Select providers
    """

    def __init__(
        self,
        registry: ProviderRegistry,
    ) -> None:

        self._registry = registry

    # =====================================================

    def start(
        self,
        provider: str,
        *,
        seconds: int,
    ) -> None:
        """
        Place a provider into cooldown.
        """

        state = self._registry.get(provider)

        state.status = ProviderStatus.COOLDOWN

        state.cooldown_until = (
            datetime.utcnow()
            + timedelta(seconds=seconds)
        )

        state.failure_count += 1

        state.last_failure = datetime.utcnow()

        logger.warning(
            "%s entered cooldown for %d seconds.",
            provider,
            seconds,
        )

    # =====================================================

    def clear(
        self,
        provider: str,
    ) -> None:
        """
        Remove cooldown.
        """

        state = self._registry.get(provider)

        state.cooldown_until = None

        state.status = ProviderStatus.AVAILABLE

        logger.info(
            "%s cooldown expired.",
            provider,
        )

    # =====================================================

    def expired(
        self,
        provider: str,
    ) -> bool:
        """
        Returns True if cooldown has expired.
        """

        state = self._registry.get(provider)

        if state.cooldown_until is None:

            return True

        return datetime.utcnow() >= state.cooldown_until

    # =====================================================

    def update(self) -> None:
        """
        Restore every provider whose cooldown has expired.
        """

        for state in self._registry:

            if (

                state.status == ProviderStatus.COOLDOWN

                and

                self.expired(
                    state.provider.name
                )

            ):

                self.clear(
                    state.provider.name
                )