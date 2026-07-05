from __future__ import annotations


class EntityTracker:
    """
    Stores entities discovered during the current session.

    Examples
    --------
    person   -> Elon Musk
    project  -> Mike
    language -> Python
    company  -> Tesla
    file     -> main.py
    """

    # =====================================================

    def __init__(self) -> None:

        self._entities: dict[str, str] = {}

    # =====================================================
    # CRUD
    # =====================================================

    def set(
        self,
        key: str,
        value: str,
    ) -> None:

        if key and value:
            self._entities[key] = value

    # -----------------------------------------------------

    def get(
        self,
        key: str,
        default: str | None = None,
    ) -> str | None:

        return self._entities.get(key, default)

    # -----------------------------------------------------

    def remove(
        self,
        key: str,
    ) -> None:

        self._entities.pop(key, None)

    # -----------------------------------------------------

    def clear(self) -> None:

        self._entities.clear()

    # =====================================================
    # Read-only Access
    # =====================================================

    @property
    def entities(self) -> dict[str, str]:
        """
        Returns a copy of all tracked entities.
        """

        return dict(self._entities)

    # -----------------------------------------------------

    def items(self):

        return self._entities.items()

    # -----------------------------------------------------

    def keys(self):

        return self._entities.keys()

    # -----------------------------------------------------

    def values(self):

        return self._entities.values()

    # =====================================================
    # Helpers
    # =====================================================

    def __contains__(
        self,
        key: str,
    ) -> bool:

        return key in self._entities

    # -----------------------------------------------------

    def __len__(self) -> int:

        return len(self._entities)

    # -----------------------------------------------------

    def __iter__(self):

        return iter(self._entities.items())

    # -----------------------------------------------------

    def __repr__(self) -> str:

        return f"{self.__class__.__name__}({self._entities})"