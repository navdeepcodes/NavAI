from urllib.parse import quote

from logs.logger import logger

from tools.browser.open_url import open_url


def search_browser(
    query: str
) -> str:

    if not query:

        raise ValueError(
            "Search query is required."
        )

    logger.info(
        f"Searching: {query}"
    )

    url = (
        "https://www.google.com/search?q="
        + quote(query)
    )

    return open_url(
        url
    )