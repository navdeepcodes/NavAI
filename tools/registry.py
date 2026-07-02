from tools.browser import (
    open_browser,
    open_url,
    search,
)

TOOLS = [
    open_browser,
    open_url,
    search,
]

FUNCTION_MAP = {
    "open_browser": open_browser,
    "open_url": open_url,
    "search": search,
}


def execute(function_name: str, **kwargs):

    if function_name not in FUNCTION_MAP:
        raise ValueError(
            f"Unknown function: {function_name}"
        )

    return FUNCTION_MAP[function_name](**kwargs)