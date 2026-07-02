from abc import ABC, abstractmethod


class BaseProvider(ABC):

    @abstractmethod
    def chat(self, message: str) -> str:
        """
        Send a message to the AI model.
        """
        pass