from __future__ import annotations

from typing import Iterator

from logs.logger import logger

from brain.providers.base_llm_provider import BaseLLMProvider
from brain.providers.provider_state import ProviderState


class ProviderRegistry:
    """
    Central registry for all LLM providers.

    Responsibilities
    ----------------
    • Register providers
    • Store ProviderState objects
    • Retrieve providers
    • Enumerate providers

    Never
    -----
    • Route requests
    • Execute requests
    • Perform health checks
    • Apply cooldown logic
    """

    def __init__(self) -> None:

        self._providers: dict[str, ProviderState] = {}

    # =====================================================

    def register(
        self,
        provider: BaseLLMProvider,
    ) -> None:

        state = ProviderState(
            provider=provider,
        )

        self._providers[
            provider.name.lower()
        ] = state

        logger.info(
            "Registered provider: %s",
            provider.name,
        )

    # =====================================================

    def unregister(
        self,
        name: str,
    ) -> None:

        removed = self._providers.pop(
            name.lower(),
            None,
        )

        if removed:

            logger.info(
                "Unregistered provider: %s",
                removed.provider.name,
            )

    # =====================================================

    def exists(
        self,
        name: str,
    ) -> bool:

        return name.lower() in self._providers

    # =====================================================

    def get(
        self,
        name: str,
    ) -> ProviderState | None:

        return self._providers.get(
            name.lower()
        )

    # =====================================================

    def by_name(
        self,
        name: str,
    ) -> ProviderState | None:

        return self.get(name)

    # =====================================================

    def provider(
        self,
        name: str,
    ) -> BaseLLMProvider | None:

        state = self.get(name)

        if state is None:

            return None

        return state.provider

    # =====================================================

    def states(
        self,
    ) -> tuple[ProviderState, ...]:

        return tuple(
            self._providers.values()
        )

    # =====================================================

    def providers(
        self,
    ) -> tuple[BaseLLMProvider, ...]:

        return tuple(

            state.provider

            for state in self._providers.values()

        )

    # =====================================================

    def names(
        self,
    ) -> tuple[str, ...]:

        return tuple(

            state.provider.name

            for state in self._providers.values()

        )

    # =====================================================

    def clear(
        self,
    ) -> None:

        self._providers.clear()

    # =====================================================

    def __contains__(
        self,
        name: str,
    ) -> bool:

        return self.exists(name)

    # =====================================================

    def __len__(
        self,
    ) -> int:

        return len(self._providers)

    # =====================================================

    def __iter__(
        self,
    ) -> Iterator[ProviderState]:

        return iter(
            self._providers.values()
        )