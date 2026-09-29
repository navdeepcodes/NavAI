"""Quitting the packaged app must not raise.

The windowed build has no console, so sys.stdout and sys.stderr are None.
run() flushed them unguarded before exiting, and every quit ended in an
"Unhandled exception in script" dialog that kept the process alive.
"""
import sys


def test_flushing_with_no_console_does_not_raise(monkeypatch):
    from ui.app import _flush_std_streams

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _flush_std_streams()


def test_flushing_still_flushes_a_real_stream(monkeypatch):
    from ui.app import _flush_std_streams

    flushed = []

    class Stream:
        def flush(self):
            flushed.append(True)

    monkeypatch.setattr(sys, "stdout", Stream())
    monkeypatch.setattr(sys, "stderr", Stream())
    _flush_std_streams()
    assert len(flushed) == 2
