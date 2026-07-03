from brain.planner_validator import PlannerValidator
from brain.task import Task


def main():

    validator = PlannerValidator()

    # -------------------------------
    # Valid Task
    # -------------------------------

    valid = Task(
        id=1,
        description="Open Google",
        tool="browser",
        action="open_url",
        arguments={
            "url": "https://google.com"
        }
    )

    result = validator.validate([valid])

    assert len(result) == 1

    # -------------------------------
    # Invalid Tool
    # -------------------------------

    invalid_tool = Task(
        id=2,
        description="Invalid",
        tool="fake_tool",
        action="run",
        arguments={}
    )

    result = validator.validate([invalid_tool])

    assert len(result) == 0

    # -------------------------------
    # Invalid Action
    # -------------------------------

    invalid_action = Task(
        id=3,
        description="Invalid",
        tool="browser",
        action="explode",
        arguments={}
    )

    result = validator.validate([invalid_action])

    assert len(result) == 0

    # -------------------------------
    # Missing Arguments
    # -------------------------------

    missing_args = Task(
        id=4,
        description="Missing URL",
        tool="browser",
        action="open_url",
        arguments={}
    )

    result = validator.validate([missing_args])

    assert len(result) == 0

    print("✅ PlannerValidator passed.")


if __name__ == "__main__":
    main()