from tools.tool_registry import ToolRegistry

registry = ToolRegistry()

print("\nRegistered Tools:")

for tool in registry.available():

    print("-", tool)