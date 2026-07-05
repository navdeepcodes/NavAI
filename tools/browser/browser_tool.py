from __future__ import annotations

from tools.base_tool import BaseTool
from tools.tool_context import ToolContext
from tools.tool_metadata import ToolMetadata
from tools.tool_permission import Permission
from tools.tool_result import ToolResult

from tools.browser.browser_session import BrowserSession
from tools.browser.open_browser import open_browser
from tools.browser.open_url import open_url
from tools.browser.search_browser import search_browser


class BrowserTool(BaseTool):

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def __init__(self) -> None:

        super().__init__()

        self.session = BrowserSession()

    # ---------------------------------------------------------
    # Metadata
    # ---------------------------------------------------------

    @property
    def metadata(self) -> ToolMetadata:

        return ToolMetadata(

            name="browser",

            description="Open the browser, open URLs and perform web searches.",

            category="browser",

            tags=[
                "browser",
                "web",
                "internet",
                "search",
            ],

        )

    # ---------------------------------------------------------
    # Permission
    # ---------------------------------------------------------

    @property
    def permission(self) -> Permission:

        return Permission.BROWSER

    # ---------------------------------------------------------
    # Supported Actions
    # ---------------------------------------------------------

    @property
    def actions(self):

        return {

            "open_browser": self._open_browser,

            "open_url": self._open_url,

            "search": self._search,

        }

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def validate(
        self,
        action: str,
        **kwargs,
    ) -> bool:

        validators = {

            "open_browser": lambda: True,

            "open_url": lambda: bool(
                kwargs.get("url")
            ),

            "search": lambda: bool(
                kwargs.get("query")
            ),

        }

        validator = validators.get(action)

        return validator() if validator else False

    # ---------------------------------------------------------
    # Execute
    # ---------------------------------------------------------

    def execute(
        self,
        action: str,
        context: ToolContext,
        **kwargs,
    ) -> ToolResult:

        handler = self.actions.get(action)

        if handler is None:

            return ToolResult(

                success=False,

                tool=self.metadata.name,

                action=action,

                error=f"Unknown browser action '{action}'.",

            )

        try:

            result = handler(**kwargs)

            return ToolResult(

                success=True,

                tool=self.metadata.name,

                action=action,

                message=str(result),

            )

        except Exception as exc:

            return ToolResult(

                success=False,

                tool=self.metadata.name,

                action=action,

                error=str(exc),

            )

    # ---------------------------------------------------------
    # Action Handlers
    # ---------------------------------------------------------

    def _open_browser(
        self,
        **kwargs,
    ) -> str:

        result = open_browser()

        self.session.page_loaded = True

        return result

    # ---------------------------------------------------------

    def _open_url(
        self,
        url: str,
        **kwargs,
    ) -> str:

        result = open_url(url)

        self.session.update(
            url=url,
        )

        return result

    # ---------------------------------------------------------

    def _search(
        self,
        query: str,
        **kwargs,
    ) -> str:

        result = search_browser(query)

        return result