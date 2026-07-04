from __future__ import annotations

from abc import ABC, abstractmethod

from brain.llm.llm_request import LLMRequest
from brain.llm.provider_response import ProviderResponse
from brain.providers.base_provider import BaseProvider


class BaseLLMProvider(BaseProvider, ABC):
    """
    Base interface implemented by every LLM provider.

    Providers are thin adapters around external APIs.

    Responsibilities
    ----------------
    • Send requests to the model
    • Translate SDK responses
    • Return ProviderResponse

    Providers MUST NOT:
    -------------------
    • Build prompts
    • Manage conversations
    • Perform reasoning
    • Select providers
    • Execute tools
    • Manage memory
    """

    # =====================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    # =====================================================

    @property
    @abstractmethod
    def capability(self):
        """
        ProviderCapability describing supported features.
        """
        ...

    # =====================================================

    @abstractmethod
    def generate(
        self,
        request: LLMRequest,
    ) -> ProviderResponse:
        """
        Execute a completion request.
        """
        ...

    # =====================================================

    def health_check(self) -> bool:
        """
        Providers may override this with a real API ping.

        Default implementation assumes the provider
        is available if construction succeeded.
        """
        return True