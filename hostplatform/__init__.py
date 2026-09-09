"""OS-facing services Mike Core must not know the shape of.

Named `hostplatform` rather than `platform` deliberately — a top-level
package called `platform` would shadow Python's own stdlib module for every
file in the repo that does `import platform` (there are several, including
inside this package), since the repo root sits on `sys.path` ahead of the
standard library search path. That is exactly the kind of silent, sitewide
breakage this whole effort exists to design out of. So: `hostplatform`.

Each module here is a cohesive service, not a slot in one generic manager:

    storage     where persistent data lives (preferences, databases, logs,
                cache, the neural-voice install)
    processes   spawning and fully terminating child processes and their
                descendants
    shell       opening a URL, file or application through the OS shell
    capture     screen capture
    desktop     tray presence, notifications, frontmost app, reduced motion

Each exposes `get_*()` dispatching on `platform.system()` (the real stdlib
one) that raises a clear error for an operating system with no adapter yet,
the same rule `computer/base.py` already established. High-level Mike code
imports the service, never the OS API underneath it.
"""
