"""Mike's own log messages must survive Windows' default codepage.

The regression this guards was silent and total: `logs/logger.py` opened
its FileHandler with no encoding, so on Windows it used cp1252. Mike logs
characters outside that set -- an arrow in "Tool success: filesystem.
create_file -> ...", em dashes in several modules, a tick in the OAuth
flow, a microphone glyph in the mic module. Each one raised
UnicodeEncodeError *inside logging*, which discards the record and prints
"--- Logging error ---" with a traceback instead.

Found on a real end-to-end run, where every successful tool call dumped a
traceback into the log while the tool itself had worked perfectly. The
danger is that it looks like the tool failed when nothing did.

Asserted at the handler rather than by grepping the codebase for exotic
characters: that list was 37 lines long and would only stay correct until
somebody typed an em dash again.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

# Characters taken from real log calls in this codebase.
AWKWARD = "arrow → dash — tick ✅ mic \U0001F3A4 box └"


def test_the_log_file_handler_can_encode_what_mike_actually_logs():
    from logs.logger import logger

    handlers = [h for h in logging.getLogger().handlers
                if isinstance(h, logging.FileHandler)]
    assert handlers, "expected a FileHandler on the root logger"

    for handler in handlers:
        encoding = (handler.encoding or "").lower().replace("-", "_")
        assert encoding in ("utf_8", "utf8"), (
            f"log file handler uses {handler.encoding!r}; on Windows a "
            "non-UTF-8 handler silently drops any record containing a "
            "character the codepage cannot encode"
        )
        # The real proof: the stream itself accepts the bytes.
        handler.stream.write(AWKWARD + "\n")
        handler.flush()

    logger.info("Tool success: %s.%s → %s", "filesystem", "create_file", "ok")


def test_logging_a_non_cp1252_message_raises_nothing():
    """logging swallows encoding failures into its own error path rather
    than raising, so this asserts on that path being clean -- a bare call
    that "worked" was exactly how this shipped."""
    from logs.logger import logger

    seen: list[str] = []
    original = logging.Handler.handleError

    def record_error(self, record):  # noqa: ANN001
        seen.append(str(record.msg))
        return original(self, record)

    logging.Handler.handleError = record_error
    try:
        logger.info(AWKWARD)
        for handler in logging.getLogger().handlers:
            handler.flush()
    finally:
        logging.Handler.handleError = original

    assert not seen, f"logging reported an error handling: {seen}"
