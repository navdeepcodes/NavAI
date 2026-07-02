import subprocess
import urllib.parse

from config.settings import DEFAULT_BROWSER
from logs.logger import logger
from tools.base_tool import BaseTool


class BrowserTool(BaseTool):

    @property
    def name(self):
        return "browser"

    def execute(self, action, **kwargs):

        if action == "open_browser":
            return self.open_browser()

        elif action == "open_url":
            return self.open_url(kwargs.get("url"))

        elif action == "search":
            return self.search(kwargs.get("query"))

        logger.warning(f"Unknown browser action: {action}")
        return False

    def open_browser(self):

        logger.info(f"Opening {DEFAULT_BROWSER}")

        subprocess.run(
            ["open", "-a", DEFAULT_BROWSER]
        )

        return True

    def open_url(self, url):

        logger.info(f"Opening URL: {url}")

        subprocess.run(
            ["open", "-a", DEFAULT_BROWSER, url]
        )

        return True

    def search(self, query):

        encoded = urllib.parse.quote(query)

        url = f"https://www.google.com/search?q={encoded}"

        return self.open_url(url)