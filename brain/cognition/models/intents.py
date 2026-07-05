from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    """
    Mike's canonical user intentions.

    UnderstandingEngine should always normalize
    to one of these values.
    """

    UNKNOWN = "unknown"

    # Conversation
    GREETING = "greeting"
    FAREWELL = "farewell"
    SMALL_TALK = "small_talk"

    # Information
    INFORMATION_REQUEST = "information_request"
    EXPLANATION = "explanation"
    QUESTION = "question"

    # Creation
    WRITE = "write"
    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    CODE = "code"

    # Computer
    SYSTEM_CONTROL = "system_control"
    FILE_OPERATION = "file_operation"
    APPLICATION_CONTROL = "application_control"
    WEB_ACTION = "web_action"
    TERMINAL_ACTION = "terminal_action"

    # Memory
    MEMORY_STORE = "memory_store"
    MEMORY_RECALL = "memory_recall"
    MEMORY_UPDATE = "memory_update"

    # Planning
    TASK_REQUEST = "task_request"

    # Misc
    CLARIFICATION = "clarification"

    UNKNOWN_REQUEST = "unknown_request"