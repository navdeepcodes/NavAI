from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """
    Base interface for every AI provider.

    This class contains only functionality common to all providers.

    Provider-specific request execution belongs in subclasses
    such as BaseLLMProvider.

    Responsibilities
    ----------------
    • Provider identity
    • Availability checks

    Never
    -----
    • Execute prompts
    • Build prompts
    • Route requests
    • Manage conversations
    • Execute tools
    """

    # =========================================================

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable provider name.

        Example:
            Gemini
            Groq
            Ollama
            OpenRouter
        """
        ...

    # =========================================================

    def health_check(self) -> bool:
        """
        Verify that the provider is available.

        Providers may override this to perform an actual API
        request or connectivity check.

        Returns
        -------
        bool
            True if the provider is healthy.
        """
        return True