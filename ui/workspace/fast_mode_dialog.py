"""Turning on Fast mode: one card, three screens, as few clicks as there can be.

    offer    what it is, in a sentence, and one button     (first run only)
    browser  "Sign in with Google, then Authorize"         (Cloudflare's page)
    done     Fast mode is on

Cloudflare's own page does the rest: "Sign in with Google" makes a free
Cloudflare account if the student doesn't have one, so the whole thing is
Connect -> Sign in with Google -> Authorize. Mike finds the account itself;
nobody copies an ID or a key. Same card, marks and buttons as the account
dialog, so it reads as part of Mike.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLayout, QVBoxLayout

from ui.panel import style
from ui.workspace.account_dialog import AuthDialog, _Mark, _Page, _Pages, _btn, _qss

#: Long enough to make a Cloudflare account on the way (Google sign-in, and
#: Cloudflare's own first-run screens), short enough not to wait forever.
CONNECT_TIMEOUT = 900


class FastModeDialog(QDialog):
    """accept()s once Fast mode is connected."""

    SHADOW = AuthDialog.SHADOW
    WIDTH = AuthDialog.WIDTH
    paintEvent = AuthDialog.paintEvent        # the same card

    #: Connecting finished: an error to show, or "" when connected.
    _finished = Signal(str)

    def __init__(self, parent=None, *, start: bool = False) -> None:
        super().__init__(parent)
        self._cancel: threading.Event | None = None
        self._url = ""
        self._failed = False            # the last try ended in an error
        self.setWindowTitle("Mike — Fast mode")
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(_qss())
        self._finished.connect(self._connected)
        self._build()
        if start:
            QTimer.singleShot(0, self._connect)
        else:
            self._go(self.p_offer)

    # ── card ─────────────────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        s = self.SHADOW
        outer.setContentsMargins(s + 34, s + 24, s + 34, s + 26)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SetFixedSize)
        top = QHBoxLayout()
        top.addWidget(_Mark(), 0, Qt.AlignLeft | Qt.AlignTop)
        top.addStretch(1)
        close = _btn("×", "close", QFont.Weight.Normal, 18)
        close.setFixedSize(30, 30)
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self._dismiss)
        top.addWidget(close, 0, Qt.AlignTop)
        outer.addLayout(top)
        outer.addSpacing(18)
        self.stack = _Pages()
        self.stack.setFixedWidth(self.WIDTH - 68)
        outer.addWidget(self.stack)
        for page in (self._build_offer(), self._build_browser(), self._build_done()):
            self.stack.addWidget(page)

    def _build_offer(self) -> _Page:
        from ui.panel.mike_panel import _this_machine
        here = _this_machine()
        page = _Page("Answers in seconds, free",
                     "Mike can use a free Cloudflare account to answer in about two seconds "
                     "instead of fifteen or twenty. It takes a minute: sign in with Google, "
                     "then click Authorize.<br><br>"
                     f"What you type or say goes to Cloudflare to be answered; screenshots "
                     f"stay on {here}. "
                     f"Offline, or once the day's free allowance is used, Mike uses the model "
                     f"on {here}.")
        go = page.add(_btn("Connect — it's free", "primary"))
        go.clicked.connect(self._connect)
        later = page.add(_btn("Not now", "link", QFont.Weight.Normal, style.SMALL))
        later.clicked.connect(self.reject)
        self.p_offer = page
        return page

    def _build_browser(self) -> _Page:
        page = _Page("Continue in your browser",
                     "On Cloudflare's page, choose <b>Sign in with Google</b> — it makes you "
                     "a free Cloudflare account if you don't have one — then click "
                     "<b>Authorize</b>. Mike is waiting here.")
        again = page.add(_btn("Open Cloudflare again", "provider", QFont.Weight.Medium))
        again.clicked.connect(self._reopen)
        page.add_error()
        cancel = page.add(_btn("Cancel", "link", QFont.Weight.Normal, style.SMALL))
        cancel.clicked.connect(self._dismiss)
        self.p_browser = page
        return page

    def _build_done(self) -> _Page:
        page = _Page("Fast mode is on", "Mike answers in seconds now. You can switch it off "
                                        "any time in Settings → General.")
        done = page.add(_btn("Done", "primary"))
        done.clicked.connect(self.accept)
        self.p_done = page
        return page

    def _go(self, page: _Page) -> None:
        page.show_error("")
        self.stack.setCurrentWidget(page)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self._dismiss()
            return
        super().keyPressEvent(e)

    # ── connecting ───────────────────────────────────────────────────────
    def _connect(self) -> None:
        from account import cloudflare
        self._go(self.p_browser)
        self._cancel = threading.Event()
        cancel = self._cancel

        def open_browser(url: str) -> None:
            self._url = url
            self._reopen()

        def work() -> None:
            try:
                cloudflare.connect(open_browser=open_browser, timeout=CONNECT_TIMEOUT,
                                   cancel=cancel)
                self._finished.emit("")
            except cloudflare.CloudflareError as exc:
                if not cancel.is_set():
                    self._finished.emit(str(exc))
            except Exception:  # never leave the card waiting on nothing
                from logs.logger import logger
                logger.exception("Connecting Cloudflare failed")
                self._finished.emit("Connecting didn't work. Try again.")

        threading.Thread(target=work, name="cloudflare-connect", daemon=True).start()

    def _reopen(self) -> None:
        if self._failed:
            # The last try has ended and nothing listens for its link any more
            # (measured: reopened, authorized -- "127.0.0.1 refused to
            # connect"). A new try, then.
            self._failed = False
            self._connect()
            return
        if self._url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self._url))

    def _connected(self, error: str) -> None:
        if error:
            self._failed = True
            self.p_browser.show_error(error)
            return
        self._go(self.p_done)
        self._come_forward()

    def _come_forward(self) -> None:
        """Back from the browser: Mike, not the tab, is where it finishes."""
        self.raise_()
        self.activateWindow()
        try:
            from hostplatform.foreground import bring_to_front
            bring_to_front(int(self.winId()))
        except Exception:
            pass

    def _dismiss(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
        self.reject()


def ask(parent=None, *, start: bool = False) -> bool:
    """Open the card and wait. True once Fast mode is connected. `start`
    skips the offer (the person already clicked Connect)."""
    dlg = FastModeDialog(parent, start=start)
    if parent is not None and parent.isVisible():
        g = parent.window().frameGeometry()
        dlg.adjustSize()
        dlg.move(g.center().x() - dlg.width() // 2, g.center().y() - dlg.height() // 2 - 20)
    return dlg.exec() == QDialog.Accepted
