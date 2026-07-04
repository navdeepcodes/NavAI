from __future__ import annotations


class ResponseFormatter:
    """
    Future formatting layer.

    Markdown cleanup.

    Lists.

    Tables.

    Code formatting.

    Citations.

    etc.
    """

    def format(
        self,
        text: str,
    ) -> str:

        return text.strip()