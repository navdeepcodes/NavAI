from tools.tool_registry import ToolRegistry

_registry = ToolRegistry()


def get_tool(name: str):
    tool = _registry.get(name)

    assert tool is not None, f"Tool '{name}' not found."

    return tool