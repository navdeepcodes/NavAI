from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar("T")


class BaseParser(ABC, Generic[T]):
    """
    Base class for every parser used by the LLM layer.
    """

    @abstractmethod
    def parse(
        self,
        text: str,
    ) -> T | None:
        """
        Convert raw LLM text into a structured object.
        """
        raise NotImplementedError