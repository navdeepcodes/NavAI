from __future__ import annotations

import platform
from pathlib import Path

from config.settings import DEFAULT_BROWSER

from brain.self.models.system_profile_model import (
    SystemProfileModel,
)


SYSTEM_PROFILE = SystemProfileModel(

    operating_system=platform.system(),

    python_version=platform.python_version(),

    cpu=platform.processor(),

    architecture=platform.machine(),

    hostname=platform.node(),

    home_directory=str(Path.home()),

    workspace=str(Path.cwd()),

    default_browser=DEFAULT_BROWSER,
)