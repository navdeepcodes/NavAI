from dataclasses import dataclass, field

from brain.models.conversation import Conversation


@dataclass(slots=True)
class Session:

    id: str

    conversation: Conversation = field(
        default_factory=Conversation
    )

    provider: str = ""

    metadata: dict = field(
        default_factory=dict
    )