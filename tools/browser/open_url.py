from __future__ import annotations

from hostplatform import shell
from logs.logger import logger


def open_url(url: str) -> str:
    if not url:
        raise ValueError("URL is required.")

    normalized = shell.normalize_url(url)
    logger.info(f"Opening URL: {normalized}")
    shell.open_url(url)
    return f"Opened {normalized}"
