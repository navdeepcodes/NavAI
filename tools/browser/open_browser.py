from __future__ import annotations

from config.settings import DEFAULT_BROWSER
from hostplatform import shell
from logs.logger import logger


def open_browser() -> str:
    """
    Open the user's default browser. The OS mechanism for it lives in
    hostplatform.shell.
    """
    logger.info(f"Opening browser: {DEFAULT_BROWSER}")
    shell.open_browser()
    return "Browser opened successfully."
