from abc import ABC, abstractmethod


class BaseTool(ABC):

    @property
    @abstractmethod
    def name(self):
        ...

    @abstractmethod
    def execute(
        self,
        **kwargs
    ):
        ...