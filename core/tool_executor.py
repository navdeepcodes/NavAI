from tools.browser import BrowserTool


class ToolExecutor:

    def __init__(self):

        self.browser = BrowserTool()

    def execute(
        self,
        function_name,
        arguments
    ):

        if function_name == "open_browser":

            return self.browser.open_browser()

        elif function_name == "open_url":

            return self.browser.open_url(
                arguments["url"]
            )

        elif function_name == "search":

            return self.browser.search(
                arguments["query"]
            )

        raise ValueError(
            f"Unknown function {function_name}"
        )