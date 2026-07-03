from tests.test_utils import get_tool


def main():

    terminal = get_tool("terminal")

    assert terminal.validate(
        "run",
        command="pwd"
    )

    assert not terminal.validate(
        "run"
    )

    print("✅ TerminalTool passed.")


if __name__ == "__main__":

    main()