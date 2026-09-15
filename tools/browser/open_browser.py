from __future__ import annotations

from config.settings import DEFAULT_BROWSER
from hostplatform import desktop
from logs.logger import logger


def open_browser() -> str:
    """
    Open the user's default web browser.
    """

    logger.info(
        f"Opening browser: {DEFAULT_BROWSER}"
    )

    return desktop.open_browser(DEFAULT_BROWSER)
