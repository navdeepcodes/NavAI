"""brain.reply_style: the backstop for the two persona tells the model keeps
producing against instructions.

These are the exact shapes measured coming out of the real model across three
system-prompt rewrites -- the "vent or a distraction?" support-menu and a
stray emoji on good news -- plus the ordinary replies that must pass through
untouched, since a guard that mangles normal speech is worse than the tell.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.reply_style import humanize_reply


def test_distraction_menu_collapses_to_the_single_question():
    out = humanize_reply(
        "I hear you. Want to vent about what's been going wrong, "
        "or should I distract you for a bit?"
    )
    assert out == "I hear you. Want to vent about what's been going wrong?"


def test_distraction_menu_with_take_your_mind_off():
    out = humanize_reply(
        "Sounds frustrating. Want to vent about what's going wrong, or should I "
        "help you find something distracting to take your mind off it?"
    )
    assert out == "Sounds frustrating. Want to vent about what's going wrong?"


def test_rather_phrasing_is_also_caught():
    out = humanize_reply(
        "I'm sorry to hear that. Want to talk about it, or would you rather I "
        "find a distraction?"
    )
    assert out == "I'm sorry to hear that. Want to talk about it?"


def test_distraction_offer_as_its_own_sentence_is_removed():
    # The model also splits the offer off into a second sentence; the comma
    # form isn't the only one, so both are removed.
    out = humanize_reply(
        "That sounds frustrating. Want to vent about what's been going wrong? "
        "Or maybe I can help you find something to take your mind off it for a bit?"
    )
    assert out == "That sounds frustrating. Want to vent about what's been going wrong?"


def test_stray_emoji_is_removed():
    out = humanize_reply("That's huge! I'm so glad it finally works. \U0001F389")
    assert "\U0001F389" not in out
    assert out == "That's huge! I'm so glad it finally works."


def test_an_ordinary_or_choice_is_left_alone():
    # No distraction keyword -> not a support menu -> untouched.
    text = "Should I open this in Chrome or Firefox?"
    assert humanize_reply(text) == text


def test_a_plain_question_is_left_alone():
    text = "Can you show me the script and the error message?"
    assert humanize_reply(text) == text


def test_a_single_open_question_is_kept():
    # Asking once is human; only the menu-of-options shape is the problem.
    text = "Want to talk about what's going wrong?"
    assert humanize_reply(text) == text


def test_casual_reply_untouched():
    text = "nothing much, just hanging out. how about you?"
    assert humanize_reply(text) == text


def test_empty_is_safe():
    assert humanize_reply("") == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
    print("\nAll reply_style tests passed.")
