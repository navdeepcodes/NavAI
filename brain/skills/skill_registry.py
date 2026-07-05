from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

import brain.skills

from logs.logger import logger

from brain.skills.base_skill import BaseSkill


class SkillRegistry:
    """
    Automatically discovers and registers every installed skill.

    Features
    --------
    • Recursive discovery
    • Automatic registration
    • Duplicate protection
    • Metadata validation
    • Reload support
    """

    # =====================================================

    SKIP_MODULES = {
        "__init__",
        "__pycache__",
        "base_skill",
        "skill_metadata",
        "skill_result",
        "skill_registry",
        "skill_manager",
    }

    # =====================================================

    def __init__(self) -> None:

        self.skills: dict[str, BaseSkill] = {}

        self._visited: set[str] = set()

        self._registered: set[type] = set()

        self._discover_package(
            brain.skills,
        )

    # =====================================================

    def _discover_package(
        self,
        package: ModuleType,
    ) -> None:

        logger.info(
            "Discovering skills: %s",
            package.__name__,
        )

        for module_info in pkgutil.iter_modules(
            package.__path__,
        ):

            name = module_info.name

            if (
                name.startswith("_")
                or name in self.SKIP_MODULES
            ):
                continue

            full_name = f"{package.__name__}.{name}"

            if full_name in self._visited:

                continue

            self._visited.add(
                full_name,
            )

            try:

                module = importlib.import_module(
                    full_name,
                )

            except Exception:

                logger.exception(
                    "Failed importing skill module '%s'.",
                    full_name,
                )

                continue

            self._register_module(
                module,
            )

            if hasattr(
                module,
                "__path__",
            ):

                self._discover_package(
                    module,
                )

    # =====================================================

    def _register_module(
        self,
        module: ModuleType,
    ) -> None:

        for _, cls in inspect.getmembers(
            module,
            inspect.isclass,
        ):

            if cls is BaseSkill:

                continue

            if not issubclass(
                cls,
                BaseSkill,
            ):

                continue

            if inspect.isabstract(
                cls,
            ):

                continue

            if cls in self._registered:

                continue

            try:

                skill = cls()

                self.register(
                    skill,
                )

                self._registered.add(
                    cls,
                )

            except Exception:

                logger.exception(
                    "Failed registering skill '%s'.",
                    cls.__name__,
                )

    # =====================================================

    def register(
        self,
        skill: BaseSkill,
    ) -> None:

        metadata = skill.metadata

        if not metadata.name:

            raise ValueError(
                "Skill name cannot be empty."
            )

        if metadata.name in self.skills:

            logger.warning(
                "Duplicate skill '%s' ignored.",
                metadata.name,
            )

            return

        logger.info(
            "Registered skill: %s",
            metadata.name,
        )

        self.skills[
            metadata.name
        ] = skill

    # =====================================================

    def has(
        self,
        name: str,
    ) -> bool:

        return name in self.skills

    # =====================================================

    def get(
        self,
        name: str,
    ) -> BaseSkill | None:

        return self.skills.get(
            name,
        )

    # =====================================================

    def all(
        self,
    ) -> list[BaseSkill]:

        return list(
            self.skills.values(),
        )

    # =====================================================

    def available(
        self,
    ) -> list[str]:

        return sorted(
            self.skills.keys(),
        )

    # =====================================================

    def reload(
        self,
    ) -> None:

        logger.info(
            "Reloading skills...",
        )

        self.skills.clear()

        self._visited.clear()

        self._registered.clear()

        self._discover_package(
            brain.skills,
        )