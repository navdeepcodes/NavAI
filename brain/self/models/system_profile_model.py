from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SystemProfileModel:
    """
    Information about the machine Mike is running on.
    """

    operating_system: str

    python_version: str

    cpu: str

    architecture: str

    hostname: str

    home_directory: str

    workspace: str

    default_browser: str