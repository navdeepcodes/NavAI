from enum import Enum


class Event(str, Enum):

    THINKING_STARTED = "thinking_started"

    THINKING_FINISHED = "thinking_finished"

    RESPONSE_STARTED = "response_started"

    RESPONSE_CHUNK = "response_chunk"

    RESPONSE_FINISHED = "response_finished"

    TOOL_STARTED = "tool_started"

    TOOL_FINISHED = "tool_finished"

    PROVIDER_CHANGED = "provider_changed"

    ERROR = "error"