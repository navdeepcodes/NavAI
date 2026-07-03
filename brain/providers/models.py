from dataclasses import dataclass
from typing import Any


@dataclass
class AIResponse:

    text: str

    provider: str

    success: bool = True

    raw: Any = None