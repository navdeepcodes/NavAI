from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BrowserSession:
    """
    Stores Mike's understanding of the browser state.

    This is NOT browser automation.

    It is simply Mike's internal belief about the browser.
    """

    current_url: str | None = None

    current_domain: str | None = None

    current_title: str | None = None

    active_tab: int = 0

    page_loaded: bool = False

    history: list[str] = field(default_factory=list)

    # ---------------------------------------------------------

    def update(
        self,
        *,
        url: str,
        title: str | None = None,
    ) -> None:

        self.current_url = url
        self.current_title = title

        self.page_loaded = True

        self.history.append(url)

        self.current_domain = self._extract_domain(url)

    # ---------------------------------------------------------

    def reset(self) -> None:

        self.current_url = None
        self.current_domain = None
        self.current_title = None

        self.page_loaded = False

        self.history.clear()

    # ---------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str | None:

        if not url:
            return None

        value = (
            url.replace("https://", "")
               .replace("http://", "")
               .split("/")[0]
               .lower()
        )

        if value.startswith("www."):
            value = value[4:]

        return value

    # ---------------------------------------------------------

    @property
    def on_youtube(self) -> bool:

        return self.current_domain == "youtube.com"

    @property
    def on_google(self) -> bool:

        return self.current_domain == "google.com"

    @property
    def has_page(self) -> bool:

        return self.current_url is not None

    @property
    def is_empty(self) -> bool:

        return self.current_url is None