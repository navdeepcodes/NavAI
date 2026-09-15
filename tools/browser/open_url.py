from __future__ import annotations

from urllib.parse import urlparse

from config.settings import DEFAULT_BROWSER
from hostplatform import desktop
from logs.logger import logger


def open_url(
    url: str
) -> str:

    if not url:

        raise ValueError(
            "URL is required."
        )

    url = _normalize_url(
        url
    )

    logger.info(
        f"Opening URL: {url}"
    )

    return desktop.open_url(url, DEFAULT_BROWSER)


def _normalize_url(
    url: str
) -> str:

    url = url.strip()

    parsed = urlparse(
        url
    )

    if not parsed.scheme:

        url = f"https://{url}"

    return url
