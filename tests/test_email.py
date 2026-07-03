from tools.tool_registry import ToolRegistry


def main():

    registry = ToolRegistry()

    email = registry.get("email")

    assert email is not None

    assert email.validate(

        "send_email",

        to="test@example.com",

        subject="Test",

        body="Hello"

    )

    assert not email.validate(

        "send_email"

    )

    assert email.validate(

        "read_email"

    )

    print("✅ EmailTool passed.")


if __name__ == "__main__":

    main()