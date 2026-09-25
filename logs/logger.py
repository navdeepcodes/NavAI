import logging
import sys

from hostplatform import storage

# Used to be logs/mike.log, relative to whatever directory the process was
# launched from — the same class of bug as the OAuth token file (see
# hostplatform/storage.py). An installed app is frequently launched from a
# directory it cannot write to, and even when it can, the log ended up
# scattered into whatever folder happened to be current at launch rather than
# living beside Mike's other persistent data.
# Both handlers are pinned to UTF-8, and this is not cosmetic.
#
# A FileHandler with no encoding opens the file in the system codepage --
# cp1252 on a Windows machine -- and the console stream inherits whatever
# the console happens to be. Mike's own log messages contain characters
# outside that set: an arrow in "Tool success: filesystem.create_file -> ...",
# em dashes in several modules, a tick in the OAuth flow, a microphone
# glyph in the mic module. Every one of those raised UnicodeEncodeError
# inside logging, which swallows the record and prints a "--- Logging
# error ---" traceback instead. Observed on a real end-to-end run: every
# single successful tool call dumped a traceback into the log while the
# tool itself had worked perfectly.
#
# Fixed here rather than by hunting down ~37 individual characters across
# the codebase, because that list only stays fixed until somebody types an
# em dash again. errors="replace" is the backstop: a character this somehow
# still cannot encode degrades to a marker rather than destroying the log
# line, since a log that loses records under pressure is worse than a log
# with an odd glyph in it.
#
# Rotating, not append-forever: a plain FileHandler grew mike.log without
# limit on a machine Mike lives on for months. Four files of 2 MB keep days of
# history for "Report a problem" while never costing more than 8 MB of disk.
from logging.handlers import RotatingFileHandler

_file = RotatingFileHandler(str(storage.log_path()), maxBytes=2_000_000,
                            backupCount=3, encoding="utf-8", errors="replace")
_handlers: list[logging.Handler] = [_file]
# The packaged app is windowed: there is no console, and sys.stdout is None.
# Only log to a console when there is one.
if sys.stdout is not None:
    try:
        # Python 3.7+: retarget the console stream itself, so this survives a
        # console whose own codepage is narrower than what Mike logs.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _handlers.append(logging.StreamHandler(stream=sys.stdout))

# Attached explicitly rather than through logging.basicConfig(), which does
# nothing at all if anything else configured logging first — a library, a
# test runner — and would silently leave Mike with no log file.
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_format = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
for _h in _handlers:
    _h.setFormatter(_format)
    _root.addHandler(_h)

logger = logging.getLogger("Mike")
