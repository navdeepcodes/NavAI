from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeState:

    provider: str = ""

    thinking: bool = False

    busy: bool = False

    streaming: bool = False

    current_tool: str = ""

    current_task: str = ""

    session_id: str = ""