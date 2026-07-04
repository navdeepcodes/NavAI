from __future__ import annotations

import threading
import time

from logs.logger import logger

from brain.providers.provider_registry import ProviderRegistry
from brain.providers.cooldown_manager import CooldownManager
from brain.providers.provider_state import ProviderStatus


class ProviderHealthMonitor:
    """
    Background monitor for provider health.

    Responsibilities
    ----------------
    • Perform startup health checks
    • Recover providers after cooldown
    • Detect offline providers
    • Keep provider states synchronized

    Never:
    • Execute LLM requests
    • Select providers
    • Route requests
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        cooldowns: CooldownManager,
        interval: int = 7200,
    ) -> None:

        self._registry = registry

        self._cooldowns = cooldowns

        self._interval = interval

        self._thread: threading.Thread | None = None

        self._running = False

    # =====================================================

    def start(self) -> None:

        if self._running:

            return

        logger.info(
            "Starting Provider Health Monitor..."
        )

        self._running = True

        self._thread = threading.Thread(

            target=self._loop,

            daemon=True,

            name="ProviderHealthMonitor",

        )

        self._thread.start()

    # =====================================================

    def stop(self) -> None:

        self._running = False

    # =====================================================

    def check_all(self) -> None:
        """
        Perform an immediate health check on
        every registered provider.
        """

        logger.info(
            "Running provider health check..."
        )

        self._cooldowns.update()

        for state in self._registry:

            provider = state.provider

            if state.status == ProviderStatus.COOLDOWN:

                continue

            try:

                healthy = provider.health_check()

                if healthy:

                    if state.status != ProviderStatus.ACTIVE:

                        state.status = ProviderStatus.AVAILABLE

                else:

                    state.status = ProviderStatus.OFFLINE

            except Exception:

                logger.exception(
                    "Health check failed for %s",
                    provider.name,
                )

                state.status = ProviderStatus.OFFLINE

    # =====================================================

    def _loop(self) -> None:

        while self._running:

            try:

                self.check_all()

            except Exception:

                logger.exception(
                    "Provider health monitor crashed."
                )

            time.sleep(
                self._interval
            )