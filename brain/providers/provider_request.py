from dataclasses import dataclass

from brain.providers.task_type import TaskType


@dataclass(slots=True)
class ProviderRequest:

    task: TaskType

    requires_vision: bool = False

    requires_local: bool = False

    requires_tools: bool = False

    streaming: bool = False

    coding: bool = False