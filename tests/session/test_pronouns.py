from tests.session.base import SessionTester


def test_pronoun_resolution():

    t = SessionTester()

    t.user("Who is Elon Musk?")

    t.mike("Elon Musk is the CEO of Tesla.")

    resolved = t.resolve(
        "Where was he born?"
    )

    assert "Elon Musk" in resolved