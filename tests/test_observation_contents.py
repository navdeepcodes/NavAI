"""Reading a window must give its text, not the first 40 characters of it.

Measured in the installed app: asked what Notepad said, Mike answered from a
fragment, because an observation only ever showed value[:40] of a field.
"""
from computer.base import Observation, UIElement


def _doc(value, ref="el3", role="text_area"):
    return UIElement(ref=ref, role=role, label="Text editor", value=value)


def test_a_documents_full_text_is_in_the_observation():
    text = "Meeting at 5pm with the physics group. Bring the lab report and the calculator."
    out = Observation(app="Notepad", elements=[_doc(text)], source="accessibility").describe()
    assert text in out


def test_long_contents_are_bounded_and_say_so():
    text = "x" * (Observation.CONTENTS_CAP + 500)
    out = Observation(app="Notepad", elements=[_doc(text)], source="accessibility").describe()
    assert f"first {Observation.CONTENTS_CAP} of {len(text)} characters" in out
    assert len(out) < Observation.CONTENTS_CAP + 1000


def test_short_fields_and_buttons_are_not_repeated():
    out = Observation(app="X", source="accessibility", elements=[
        _doc("short", ref="el0", role="text_field"),
        UIElement(ref="el1", role="button", label="Save", value="x" * 100),
    ]).describe()
    assert "Contents of" not in out
