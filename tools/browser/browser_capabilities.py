from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BrowserCapability:

    name: str

    description: str

    arguments: tuple[str, ...]


BROWSER_CAPABILITIES = (

    BrowserCapability(

        name="open_browser",

        description="Launch the default browser.",

        arguments=(),

    ),

    BrowserCapability(

        name="open_url",

        description="Open a URL.",

        arguments=("url",),

    ),

    BrowserCapability(

        name="search",

        description="Search using the default search engine.",

        arguments=("query",),

    ),

    #
    # Future capabilities
    #

    BrowserCapability(

        name="search_current_page",

        description="Use the current website's search interface.",

        arguments=("query",),

    ),

    BrowserCapability(

        name="click",

        description="Click an element on the current page.",

        arguments=("selector",),

    ),

    BrowserCapability(

        name="type",

        description="Type text into the focused element.",

        arguments=("text",),

    ),

    BrowserCapability(

        name="press_key",

        description="Press a keyboard key.",

        arguments=("key",),

    ),

    BrowserCapability(

        name="wait",

        description="Wait for a number of seconds.",

        arguments=("seconds",),

    ),

)