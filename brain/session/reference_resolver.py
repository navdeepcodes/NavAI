from __future__ import annotations

import re

from brain.session.session import Session


_PRONOUNS = (
    "he",
    "him",
    "his",
    "she",
    "her",
    "hers",
    "they",
    "them",
    "their",
    "it",
    "its",
)


class ReferenceResolver:
    """
    Resolves conversational references into explicit ones.

    Example
    -------
    User:
        Who is Elon Musk?

    User:
        Where was he born?

    becomes

        Where was Elon Musk born?
    """

    def resolve(
        self,
        message: str,
        session: Session,
    ) -> str:

        person = session.entities.get("person")

        if person is None:
            return message

        resolved = message

        for pronoun in _PRONOUNS:

            resolved = re.sub(
                rf"\b{pronoun}\b",
                person,
                resolved,
                flags=re.IGNORECASE,
            )

        return resolved