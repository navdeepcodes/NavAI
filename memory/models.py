from dataclasses import dataclass
from datetime import datetime


@dataclass
class Memory:

    category: str

    content: str

    importance: int = 5

    source: str = "user"

    created_at: datetime = datetime.now()