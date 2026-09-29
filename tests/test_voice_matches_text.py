"""What Mike says is what the reply says.

Two ways the voice drifted from the text: the reply was cut into sentences at
every ". " the moment it arrived -- inside code blocks too, so half a block
reached the speech cleaner, which couldn't recognise it and read the code
aloud -- and the end of the reply was taken from the tidied text, counted in
the untidied one, so its last words were skipped or repeated.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import _isolate  # noqa: F401,E402

from ui.controller.ui_controller import _sentence_cuts  # noqa: E402


def test_sentences_are_cut_where_they_end():
    text = "Done. The site is up! Want me to open it? And"
    cuts = _sentence_cuts(text)
    assert [text[:c] for c in cuts] == ["Done.", "Done. The site is up!",
                                        "Done. The site is up! Want me to open it?"]


def test_never_inside_a_code_block():
    text = "Here it is:\n```py\nprint('a. b')\nx = 1. \n```\nThat prints it. More"
    ends = [text[:c] for c in _sentence_cuts(text)]
    assert all(e.count("```") % 2 == 0 for e in ends), "a cut inside the block"
    assert ends[-1].endswith("That prints it.")


def test_an_open_code_block_waits_for_its_end():
    text = "Try this:\n```js\nconst a = 1. b"
    assert _sentence_cuts(text) == []


def test_a_long_first_sentence_starts_speaking_at_a_pause():
    text = "So what happened is that your loop runs one step too far, and then"
    first = _sentence_cuts(text, first=True)
    assert len(first) == 1 and text[:first[0]].endswith("too far,")
    assert _sentence_cuts(text) == [], "only the very first words start early"
    assert _sentence_cuts("Sure, and", first=True) == [], "a short opening waits for its sentence"


def test_a_list_marker_or_abbreviation_does_not_end_a_sentence():
    text = "Steps:\n1. Install Node first, e.g. from the site. Then run it. Done"
    ends = [text[:c] for c in _sentence_cuts(text)]
    assert not any(e.endswith("\n1.") for e in ends), "cut after the list number"
    assert not any(e.endswith("e.g.") for e in ends), "cut after an abbreviation"
    assert ends[0].endswith("from the site.") and ends[-1].endswith("Then run it.")
