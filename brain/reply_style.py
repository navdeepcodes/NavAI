"""Enforce Mike's spoken persona on the model's own output.

The 9B local model follows most of the system prompt, but two reflexes survive
every wording of it because they are trained into the base model rather than
prompted in: it meets a negative feeling by offering a tidy menu of options
("want to vent, or should I find you a distraction?"), and it reaches for an
emoji when excited. The prompt forbids both and the model still does them a
large fraction of the time — measured across three prompt rewrites.

This is the backstop for those times: one general pass over the reply, targeting
the *shape* of the tell, not any particular app or a fixed list of phrases. It
deliberately does nothing to a plain question or a short "sorry you're stuck" —
only the distraction-menu alternative and stray emoji are removed, so a normal
reply passes through untouched.
"""
from __future__ import annotations

import re

# An offer to distract the user in place of actually engaging — the second
# half of a support menu. It shows up two ways, so it is removed two ways, and
# always keyed on a distraction word so ordinary choices ("open Chrome or
# Firefox?") are left alone.
_DISTRACTION_KEYWORD = (
    r"(?:distract|take your mind off|switch gears|"
    r"a distraction|something (?:else|different|distracting))"
)

# Its own sentence: "...going wrong? Or maybe I can take your mind off it?"
# Remove the whole sentence, keeping the punctuation that ended the one before.
_DISTRACTION_SENTENCE = re.compile(
    r"([.?!])\s+or\b[^.?!]*?" + _DISTRACTION_KEYWORD + r"[^.?!]*[.?!]",
    re.IGNORECASE,
)

# Joined to the question with a comma: "...going wrong, or should I distract
# you?" Remove from the "or" up to (not including) the end punctuation, so the
# "?" stays and closes what's left.
_DISTRACTION_CLAUSE = re.compile(
    r"[,;]?\s*\bor\b\s+(?:should|would|shall|can|do|did|will|want|i|we|you|"
    r"i'?d|we'?d|you'?d|rather|maybe|perhaps)\b[^?.!]*?"
    + _DISTRACTION_KEYWORD + r"[^?.!]*",
    re.IGNORECASE,
)

_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U0000200D"
    "\U00002B50"
    "]+",
    flags=re.UNICODE,
)


def humanize_reply(text: str) -> str:
    """Strip the two persona tells the prompt can't reliably suppress.

    Safe on text that has neither: the distraction menu only matches when a
    distraction keyword is present, and removing emoji from a reply that has
    none is a no-op. Runs on the whole reply, so it works the same whether the
    caller has a full response or one sentence of it.
    """
    if not text:
        return text

    # Standalone sentence first (it needs the punctuation before the "or" to
    # anchor to), then the comma-joined clause.
    cleaned = _DISTRACTION_SENTENCE.sub(r"\1", text)
    cleaned = _DISTRACTION_CLAUSE.sub("", cleaned)
    cleaned = _EMOJI.sub("", cleaned)

    # Tidy what the removals leave behind: a space before punctuation, a
    # doubled space, or a stranded "," / " ," before the closing mark.
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r",\s*([?.!])", r"\1", cleaned)

    return cleaned.strip()
