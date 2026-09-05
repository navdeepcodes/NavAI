from tools.browser import BrowserTool
from tools.tool_context import ToolContext


def main():
    tool = BrowserTool()

    result = tool.execute(
        action="open_browser",
        context=ToolContext()
    )

    print(result)


if __name__ == "__main__":
    # Manual smoke test only — opens a real browser window. Guarded so
    # pytest collection can't trigger it by just importing the file.
    main()
