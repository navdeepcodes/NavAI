from core.tool_executor import ToolExecutor
from tools.tool_context import ToolContext


def main():
    executor = ToolExecutor()

    result = executor.execute(
        tool_name="browser",
        action="search",
        context=ToolContext(),
        query="Mike AI Assistant"
    )

    print(result)


if __name__ == "__main__":
    # Manual smoke test only — opens a real browser and runs a real search.
    # Guarded so pytest collection can't trigger it by just importing the file.
    main()
