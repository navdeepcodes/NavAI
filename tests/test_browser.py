from tools.tool_registry import ToolRegistry


def main():

    registry = ToolRegistry()

    browser = registry.get("browser")

    assert browser is not None

    assert browser.validate(

        "open_url",

        url="https://google.com"

    )

    assert not browser.validate(

        "open_url"

    )

    print("✅ BrowserTool passed.")


if __name__ == "__main__":

    main()