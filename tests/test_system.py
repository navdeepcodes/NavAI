from tools.tool_registry import ToolRegistry


def main():

    registry = ToolRegistry()

    system = registry.get("system")

    assert system is not None

    assert system.validate("lock")

    assert system.validate("sleep")

    assert system.validate("restart")

    assert system.validate("shutdown")

    assert not system.validate("unknown_action")

    print("✅ SystemTool passed.")


if __name__ == "__main__":

    main()