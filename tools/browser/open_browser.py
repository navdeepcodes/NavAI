from __future__ import annotations

import platform
import subprocess

from config.settings import DEFAULT_BROWSER
from logs.logger import logger


def open_browser() -> str:
    """
    Open the user's default browser.
    """

    logger.info(
        f"Opening browser: {DEFAULT_BROWSER}"
    )

    system = platform.system()

    if system == "Darwin":

        subprocess.run(
            [
                "open",
                "-a",
                DEFAULT_BROWSER
            ],
            check=True
        )

    elif system == "Windows":

        subprocess.run(
            [
                "start",
                DEFAULT_BROWSER
            ],
            shell=True,
            check=True
        )

    else:

        subprocess.run(
            [
                DEFAULT_BROWSER
            ],
            check=True
        )

    return "Browser opened successfully."