from dataclasses import dataclass, field


@dataclass(slots=True)
class RuntimeContext:

    user: str = ""

    session: str = ""

    metadata: dict = field(

        default_factory=dict

    )