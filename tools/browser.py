import subprocess
import urllib.parse

from tools.base_tool import BaseTool

from config.settings import DEFAULT_BROWSER

from logs.logger import logger


class BrowserTool(BaseTool):

    @property
    def name(self):

        return "browser"

    # -----------------------------------------

    def execute(
        self,
        action: str,
        **kwargs
    ):

        if action == "open_browser":

            return self.open_browser()

        elif action == "open_url":

            return self.open_url(

                kwargs["url"]

            )

        elif action == "search":

            return self.search(

                kwargs["query"]

            )

        raise ValueError(

            f"Unknown browser action: {action}"

        )

    # -----------------------------------------

    def open_browser(self):

        logger.info(

            f"Opening {DEFAULT_BROWSER}"

        )

        subprocess.run(

            [

                "open",

                "-a",

                DEFAULT_BROWSER

            ],

            check=True

        )

        return "Browser opened successfully."

    # -----------------------------------------

    def open_url(
        self,
        url: str
    ):

        logger.info(

            f"Opening {url}"

        )

        subprocess.run(

            [

                "open",

                "-a",

                DEFAULT_BROWSER,

                url

            ],

            check=True

        )

        return f"Opened {url}"

    # -----------------------------------------

    def search(
        self,
        query: str
    ):

        encoded = urllib.parse.quote(

            query

        )

        return self.open_url(

            f"https://www.google.com/search?q={encoded}"

        )