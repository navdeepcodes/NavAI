from __future__ import annotations

import getpass
import os
import platform
import socket
from dataclasses import dataclass
from pathlib import Path

from config.settings import DEFAULT_BROWSER


# ==========================================================
# Environment
# ==========================================================


@dataclass(slots=True)
class Environment:

    os_name: str

    os_version: str

    architecture: str

    hostname: str

    username: str

    python_version: str

    cwd: str

    home: str

    default_browser: str


# ==========================================================
# Environment Manager
# ==========================================================


class EnvironmentManager:

    def __init__(self) -> None:

        self._environment = self._collect()

    # -----------------------------------------------------

    def _collect(
        self,
    ) -> Environment:

        return Environment(

            os_name=platform.system(),

            os_version=platform.release(),

            architecture=platform.machine(),

            hostname=socket.gethostname(),

            username=getpass.getuser(),

            python_version=platform.python_version(),

            cwd=str(Path.cwd()),

            home=str(Path.home()),

            default_browser=DEFAULT_BROWSER,

        )

    # -----------------------------------------------------

    @property
    def environment(
        self,
    ) -> Environment:

        return self._environment

    # -----------------------------------------------------

    def refresh(
        self,
    ) -> None:

        self._environment = self._collect()

    # -----------------------------------------------------

    def to_prompt(
        self,
    ) -> str:

        e = self._environment

        return f"""
Operating System: {e.os_name}

Version: {e.os_version}

Architecture: {e.architecture}

Python: {e.python_version}

Username: {e.username}

Hostname: {e.hostname}

Current Directory: {e.cwd}

Home Directory: {e.home}

Default Browser: {e.default_browser}
""".strip()