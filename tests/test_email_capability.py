"""Email as a deterministic capability, with the send boundary intact.

Email is the case where an API beats driving the interface. Composing through
webmail means fighting recipient autocomplete, focus stealing and a native
file picker -- measured, that put the subject line into the To field and
looped until the step budget ran out. The API takes a recipient, a subject, a
body and paths, and can be verified by reading the message back.

These tests cover the parts that must hold whether or not an account is
currently authenticated. Anything needing live credentials skips rather than
failing, so the suite stays honest on a machine without them.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _report(tmp: str) -> str:
    path = os.path.join(tmp, "report.txt")
    with open(path, "w") as handle:
        handle.write("quarterly numbers\n")
    return path


# ══ message construction ═══════════════════════════════════

def test_a_message_carries_its_attachments():
    """The previous client sent a bare MIMEText with no way to attach
    anything, so an 'email me the report' task could not be satisfied at all."""
    from tools.email.gmail_client import GmailClient

    tmp = tempfile.mkdtemp()
    message = GmailClient().build_message(
        "a@b.com", "Subject", "Body", [_report(tmp)],
    )
    names = [part.get_filename() for part in message.iter_attachments()]
    assert names == ["report.txt"], f"expected the file to be attached, got {names}"
    assert message["To"] == "a@b.com"
    assert message["Subject"] == "Subject"
    print("PASS: attachments are carried on the message")


def test_a_missing_attachment_is_refused_before_sending():
    """Failing after the message has gone is not a failure that can be undone."""
    from tools.email.gmail_client import GmailClient

    with pytest.raises(FileNotFoundError):
        GmailClient().build_message("a@b.com", "S", "B", ["/nope/missing.pdf"])
    print("PASS: a missing attachment fails before anything is sent")


def test_an_oversized_attachment_is_refused_locally():
    from tools.email.gmail_client import GmailClient, MAX_ATTACHMENT_BYTES

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "big.bin")
    with open(path, "wb") as handle:
        handle.seek(MAX_ATTACHMENT_BYTES + 1024)
        handle.write(b"\0")

    with pytest.raises(ValueError, match="limit"):
        GmailClient().build_message("a@b.com", "S", "B", [path])
    print("PASS: an oversized attachment is refused before upload")


def test_constructing_a_client_does_not_authenticate():
    """Importing or constructing must not trigger an OAuth flow. The previous
    module built a client at module scope, so importing the email tools could
    start a browser consent screen as a side effect."""
    from tools.email.gmail_client import GmailClient

    client = GmailClient()
    assert client._service is None, "authentication must be deferred until used"
    print("PASS: construction performs no authentication")


# ══ the send boundary ══════════════════════════════════════

def test_sending_requires_confirmation():
    from brain.core_tools import needs_confirmation

    assert needs_confirmation("send_email", {}), "mail leaves the machine"
    print("PASS: sending is gated")


def test_the_confirmation_names_recipient_subject_and_attachments():
    """A prompt saying 'allow send_email?' verifies nothing. The user has to
    see the actual recipient and the actual files."""
    from brain.core_tools import confirmation_detail

    tmp = tempfile.mkdtemp()
    detail = confirmation_detail("send_email", {
        "to": "someone@example.com", "subject": "Q3 report",
        "body": "Here is the summary.", "attachments": [_report(tmp)],
    })
    assert "someone@example.com" in detail
    assert "Q3 report" in detail
    assert "report.txt" in detail
    assert "cannot be recalled" in detail
    print("PASS: the confirmation shows what will actually be sent")


def test_the_confirmation_flags_an_attachment_that_is_not_there():
    """Confirming a send whose attachment is missing is how someone ends up
    mailing 'please find attached' with nothing attached."""
    from brain.core_tools import confirmation_detail

    detail = confirmation_detail("send_email", {
        "to": "a@b.com", "subject": "S", "body": "B",
        "attachments": ["/nope/missing.pdf"],
    })
    assert "MISSING" in detail
    print("PASS: a missing attachment is visible at confirmation time")


def test_composing_and_attaching_are_not_gated():
    """Only the irreversible step stops. A confirmation that fires on every
    harmless action is one the user learns to click through."""
    from brain.core_tools import needs_confirmation

    for name in ("see_ui", "list_windows", "read_file", "list_directory"):
        assert not needs_confirmation(name, {}), f"{name} is harmless"
    print("PASS: only the send boundary is gated")


def test_the_detailed_confirmation_is_what_the_user_actually_sees():
    """The rich description has to reach the prompt.

    confirmation_detail() existed and was correct while the runtime called
    describe_action(), so the user would have been asked to approve a bare
    "send_email" with no recipient and no attachment shown. A safety message
    nobody sees is not a safety message.
    """
    import tempfile

    from brain.core_tools import describe_action

    tmp = tempfile.mkdtemp()
    shown = describe_action("send_email", {
        "to": "someone@example.com", "subject": "Q3", "body": "hi",
        "attachments": [_report(tmp)],
    })
    assert "someone@example.com" in shown
    assert "report.txt" in shown
    assert "cannot be recalled" in shown

    # Other actions keep their own wording.
    assert describe_action("write_file", {"path": "/tmp/x"}) == "Write to file: /tmp/x"
    print("PASS: the send confirmation reaches the user with real detail")


def test_denial_cancels_without_sending():
    """Measured live against Gmail: the confirmation was shown, the user
    refused, and a mailbox query for that subject returned zero messages. This
    pins the wiring that makes that possible -- a denied tool call must never
    reach the send."""
    import inspect

    from brain import core_runtime

    source = inspect.getsource(core_runtime)
    assert "User denied this action." in source, (
        "a denied confirmation must short-circuit before the tool runs"
    )
    # The denial has to happen before execution, not be reported after it.
    gate = source.index("if needs_confirmation(name, args):")
    execute = source.index("self._execute_tool(", gate)
    denial = source.index("User denied this action.", gate)
    assert denial < execute, "the refusal must precede execution"
    print("PASS: a refusal short-circuits before the action runs")


# ══ failure handling ═══════════════════════════════════════

def test_a_dead_token_is_reported_as_the_user_s_to_fix(monkeypatch):
    """A revoked refresh token cannot be fixed by retrying -- only the account
    holder can complete a consent flow. Marking it retry_safe would spend the
    model's remaining steps on a call that can never succeed.

    The failure is simulated rather than provoked. An earlier version of this
    test called the real executor and skipped when it succeeded -- which meant
    that on a machine with working credentials it sent a real email to
    a@b.com on every single suite run. A test must not have side effects
    outside the machine, and "it only happens when things work" is the worst
    possible trigger for one.
    """
    from brain import core_runtime
    from tools.email import gmail_client as gc

    class Refusing:
        def send_email(self, *a, **k):
            raise gc.GmailAuthError(
                "The stored Google token is no longer valid — run "
                "auth.oauth.login() and complete the consent screen."
            )

    monkeypatch.setattr(gc, "GmailClient", lambda: Refusing())

    result = core_runtime.CoreRuntime()._execute_tool(
        "send_email", {"to": "a@b.com", "subject": "S", "body": "B"},
    )
    assert result["status"] == "error"
    assert result.get("retry_safe") is False, "an auth failure must not be retried"
    assert "login" in result["error"].lower() or "token" in result["error"].lower(), (
        f"the error should name the remedy: {result['error']!r}"
    )
    print("PASS: a dead token reports the remedy instead of inviting a retry")


def test_no_test_here_sends_real_mail():
    """A guard against the mistake above recurring.

    Nothing in this file may call the live send path. The check is on the
    source rather than on behaviour, because a behavioural check would have to
    send something to find out.
    """
    source = Path(__file__).read_text()
    body = source.split("def test_no_test_here_sends_real_mail")[0]
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "monkeypatch" in stripped:
            continue
        assert 'GmailClient().send_email' not in stripped, (
            "a unit test must never reach the real send path"
        )
    print("PASS: no test in this file can send real mail")


def test_email_is_a_capability_not_an_agent():
    """The product principle: Mike stays general. There must be no email
    planner, no mail-specific sequencing in the runtime."""
    import inspect

    from brain import core_runtime

    source = inspect.getsource(core_runtime)
    for banned in ("EmailAgent", "GmailAgent", "compose_then_send", "email_workflow"):
        assert banned not in source, f"{banned} would make Mike an application script"
    print("PASS: email is a tool, not an agent")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll email capability tests passed.")
