from __future__ import annotations

import platform
import subprocess
from urllib.parse import urlparse

from config.settings import DEFAULT_BROWSER
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

    system = platform.system()

    if system == "Darwin":

        subprocess.run(
            [
                "open",
                "-a",
                DEFAULT_BROWSER,
                url
            ],
            check=True
        )

    elif system == "Windows":

        subprocess.run(
            [
                "start",
                DEFAULT_BROWSER,
                url
            ],
            shell=True,
            check=True
        )

    else:

        subprocess.run(
            [
                DEFAULT_BROWSER,
                url
            ],
            check=True
        )

    return f"Opened {url}"


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