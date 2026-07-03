from abc import ABC, abstractmethod


class BaseProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider name.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check whether the provider is available.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def chat(
        self,
        messages
    ):
        """
        Multi-message conversation.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def complete(
        self,
        prompt: str
    ):
        """
        Stateless completion.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def vision(
        self,
        prompt: str,
        image=None
    ):
        """
        Vision / image understanding.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def stream(
        self,
        messages
    ):
        """
        Streaming response.
        """
        pass

    # -----------------------------------------

    @abstractmethod
    def supports_tools(self) -> bool:
        """
        Whether the provider supports tool/function calling.
        """
        pass