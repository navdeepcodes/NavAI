from pathlib import Path

from tools.tool_context import ToolContext
from tools.tool_registry import ToolRegistry


def main():

    registry = ToolRegistry()

    filesystem = registry.get("filesystem")

    assert filesystem is not None

    context = ToolContext()

    test_file = Path("navai_test.txt")

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    result = filesystem.execute(

        action="create_file",

        context=context,

        path=str(test_file),

    )

    assert result.success

    assert test_file.exists()

    # ---------------------------------------------------------
    # Write
    # ---------------------------------------------------------

    result = filesystem.execute(

        action="write_file",

        context=context,

        path=str(test_file),

        content="Hello NavAI",

    )

    assert result.success

    # ---------------------------------------------------------
    # Read
    # ---------------------------------------------------------

    result = filesystem.execute(

        action="read_file",

        context=context,

        path=str(test_file),

    )

    assert result.success

    assert "Hello NavAI" in result.message

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    result = filesystem.execute(

        action="delete",

        context=context,

        path=str(test_file),

    )

    assert result.success

    assert not test_file.exists()

    print("✅ FilesystemTool passed.")


if __name__ == "__main__":

    main()