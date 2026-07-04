from __future__ import annotations

from dataclasses import dataclass, field

from brain.response.response_depth import ResponseDepth


@dataclass(slots=True)
class ResponsePlan:
    """
    Describes how Mike should answer.

    This contains presentation decisions only.
    """

    depth: ResponseDepth = ResponseDepth.NORMAL

    style: str = "professional"

    format: str = "paragraph"

    sections: list[str] = field(default_factory=list)

    include_examples: bool = False

    include_next_step: bool = False

    include_summary: bool = False

    markdown: bool = True