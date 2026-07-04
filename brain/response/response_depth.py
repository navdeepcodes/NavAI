from __future__ import annotations

from enum import Enum


class ResponseDepth(str, Enum):

    MINIMAL = "minimal"

    SHORT = "short"

    NORMAL = "normal"

    DETAILED = "detailed"

    COMPREHENSIVE = "comprehensive"