"""A reopened chat brings back its recent exchanges, not all of it.

After a restart the model's cache is gone and every restored token is re-read
at this machine's cold speed (~60 tokens/s): a long chat restored whole meant
minutes before the first answer.
"""
from brain.mike_core import RESTORE_MESSAGES, MikeCore


def test_only_the_recent_exchanges_are_restored():
    core = MikeCore(host="http://127.0.0.1:11434", summary_model="unused")
    turns = []
    for i in range(40):
        turns.append({"role": "user", "content": f"question {i}"})
        turns.append({"role": "assistant", "content": f"answer {i}"})
    core.restore_conversation(turns, summary="we were writing a lab report")
    assert len(core.history) == RESTORE_MESSAGES
    assert core.history[-1]["content"] == "answer 39"
    assert core.situation_summary == "we were writing a lab report"
