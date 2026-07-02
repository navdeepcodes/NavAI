import subprocess
import urllib.parse

from config.settings import DEFAULT_BROWSER
from logs.logger import logger


def open_browser() -> str:
    """
    Opens the user's default web browser.
    """

    logger.info(f"Opening {DEFAULT_BROWSER}")

    subprocess.run(
        ["open", "-a", DEFAULT_BROWSER],
        check=True
    )

    return "Browser opened successfully."


def open_url(url: str) -> str:
    """
    Opens the given URL in the user's browser.

    Args:
        url: Website URL.
    """

    logger.info(f"Opening {url}")

    subprocess.run(
        ["open", "-a", DEFAULT_BROWSER, url],
        check=True
    )

    return f"Opened {url}"


def search(query: str) -> str:
    """
    Search Google.

    Args:
        query: Search query.
    """

    encoded = urllib.parse.quote(query)

    return open_url(
        f"https://www.google.com/search?q={encoded}"
    )