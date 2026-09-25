"""Signing in, creating an account, and changing how you sign in.

One card, in the same hand as the welcome tour, that moves between the few
screens these take — never a web view, never a browser round-trip for email:
Mike confirms with the 6-digit codes Supabase emails, typed right here.

    sign_in          email + password, or a code by email, or Google
    create           name, email, password → a code to confirm the email
    forgot           email → a code → a new password
    change_email     new address → the code(s) that confirm it
    change_password  new password (→ a code, if the project asks to confirm)
"""
from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui.panel import style

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESEND_SECONDS = 60


def _qss() -> str:
    acc = style.accent()
    return f"""
QLineEdit#field {{
    background: {style.GROUND_RAISED}; border: 1px solid {style.HAIRLINE};
    border-radius: 10px; padding: 10px 12px; color: {style.INK};
    selection-background-color: {acc};
}}
QLineEdit#field:focus {{ border: 1px solid {acc}; }}
QLineEdit#field:disabled {{ color: {style.INK_MUTE}; }}
QLineEdit#code {{
    background: {style.GROUND_RAISED}; border: 1px solid {style.HAIRLINE};
    border-radius: 12px; padding: 12px; color: {style.INK};
    selection-background-color: {acc};
}}
QLineEdit#code:focus {{ border: 1px solid {acc}; }}
QPushButton#primary {{
    background: {style.INK}; color: {style.GROUND}; border: none;
    border-radius: 10px; padding: 11px 18px;
}}
QPushButton#primary:hover {{ background: {acc}; color: #17140F; }}
QPushButton#primary:disabled {{ background: {style.INK_FAINT}; color: {style.GROUND}; }}
QPushButton#provider {{
    background: {style.GROUND_RAISED}; color: {style.INK};
    border: 1px solid {style.HAIRLINE}; border-radius: 10px; padding: 10px 18px;
}}
QPushButton#provider:hover {{ border-color: {style.INK_MUTE}; }}
QPushButton#link {{
    background: transparent; color: {style.INK_SOFT}; border: none; padding: 4px 2px;
}}
QPushButton#link:hover {{ color: {style.INK}; }}
QPushButton#link:disabled {{ color: {style.INK_FAINT}; }}
QPushButton#accentlink {{
    background: transparent; color: {acc}; border: none; padding: 4px 2px; font-weight: 600;
}}
QPushButton#close {{
    background: transparent; color: {style.INK_MUTE}; border: none;
    border-radius: 8px; font-size: 18px;
}}
QPushButton#close:hover {{ background: {style.GROUND_SUNK}; color: {style.INK}; }}
"""


def _lbl(text: str, px: int, colour: str, weight=QFont.Weight.Normal, rich=False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setFont(style.font(px, weight))
    lbl.setStyleSheet(f"color:{colour};background:transparent;")
    if rich:
        lbl.setTextFormat(Qt.RichText)
    return lbl


def _field(placeholder: str, password: bool = False) -> QLineEdit:
    f = QLineEdit()
    f.setObjectName("field")
    f.setFont(style.font(style.BODY))
    f.setPlaceholderText(placeholder)
    if password:
        f.setEchoMode(QLineEdit.Password)
    return f


def _btn(text: str, name: str, weight=QFont.Weight.DemiBold, px: int = style.BODY) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    b.setFont(style.font(px, weight))
    return b


class _GoogleMark(QWidget):
    """Google's "G", drawn in its four colours (as its sign-in guidelines ask)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(2.5, 2.5, 13, 13)
        for colour, start, span in (("#EA4335", 45, 95), ("#FBBC05", 140, 80),
                                    ("#34A853", 220, 95), ("#4285F4", 315, 45)):
            pen = QPen(QColor(colour), 3.2)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(r, start * 16, span * 16)
        p.setPen(QPen(QColor("#4285F4"), 3.2))
        p.drawLine(9.0, 9.0, 15.6, 9.0)


class _Mark(QWidget):
    """The nib on a soft accent tile — the same mark as the sidebar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 44)

    def paintEvent(self, _e) -> None:
        from ui.workspace import nib
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        tile = QColor(style.accent())
        tile.setAlpha(40)
        p.setPen(Qt.NoPen)
        p.setBrush(tile)
        p.drawRoundedRect(QRectF(0, 0, 44, 44), 12, 12)
        nib.paint_centred(p, QRectF(8, 8, 28, 28), QColor(style.accent()))


class _Pages(QWidget):
    """Like QStackedWidget, but only the showing page counts toward the size.

    (QStackedLayout's height-for-width takes the tallest page regardless of
    size policies, so any page with wrapped text made every page that tall.)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._pages: list[QWidget] = []
        self._current: QWidget | None = None

    def addWidget(self, page: QWidget) -> None:
        self._pages.append(page)
        self._col.addWidget(page)
        page.setVisible(self._current is None)
        if self._current is None:
            self._current = page

    def setCurrentWidget(self, page: QWidget) -> None:
        for w in self._pages:
            if w is not page:
                w.hide()
        page.show()
        self._current = page

    def currentWidget(self) -> QWidget | None:
        return self._current

    def count(self) -> int:
        return len(self._pages)

    def widget(self, i: int) -> QWidget:
        return self._pages[i]


class _Page(QWidget):
    """One screen of the card: a title, a line under it, then its fields."""

    def __init__(self, title: str, lead: str = "", parent=None) -> None:
        super().__init__(parent)
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(10)
        self.title = _lbl(title, 22, style.INK, QFont.Weight.DemiBold)
        self.col.addWidget(self.title)
        self.lead = _lbl(lead, style.BODY, style.INK_SOFT, rich=True)
        self.lead.setVisible(bool(lead))
        self.col.addWidget(self.lead)
        self.col.addSpacing(6)
        self.error = _lbl("", style.SMALL, style.STOP)
        self.error.hide()

    def add(self, w: QWidget) -> QWidget:
        self.col.addWidget(w)
        return w

    def add_error(self) -> None:
        self.col.addWidget(self.error)

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.setVisible(bool(text))


class AuthDialog(QDialog):
    """The account card. accept()s once the flow it was opened for succeeds."""

    SHADOW = 20
    WIDTH = 460

    #: The person chose to go on without an account (first run), or to quit
    #: (when an account is required).
    skipped = Signal()

    def __init__(self, mode: str = "sign_in", parent=None, *, first_run: bool = False,
                 required: bool = False) -> None:
        super().__init__(parent)
        from account.manager import manager
        self.mgr = manager()
        self.mode = mode
        self.first_run = first_run
        self.required = required
        self._busy = False
        self._code_ctx: dict = {}
        self._resend_left = 0
        self._resend_timer = QTimer(self)
        self._resend_timer.timeout.connect(self._tick_resend)
        self._pending_password = ""

        self.setWindowTitle("Mike — Account")
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(_qss())
        self._build()
        self._go({"sign_in": self.p_sign_in, "create": self.p_create,
                  "forgot": self.p_forgot, "change_email": self.p_change_email,
                  "change_password": self.p_change_password}.get(mode, self.p_sign_in))

    # ── card ─────────────────────────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = self.SHADOW
        for i in range(s, 0, -1):
            glow = QPainterPath()
            glow.addRoundedRect(QRectF(self.rect()).adjusted(s - i, s - i, -(s - i), -(s - i)),
                                18 + i * 0.5, 18 + i * 0.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, max(1, int(9 - i * 0.4))))
            p.drawPath(glow)
        body = QPainterPath()
        body.addRoundedRect(QRectF(self.rect()).adjusted(s, s, -s, -s), 18, 18)
        p.setBrush(QColor(style.GROUND))
        p.drawPath(body)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        s = self.SHADOW
        outer.setContentsMargins(s + 34, s + 24, s + 34, s + 26)
        outer.setSpacing(0)
        # The card is always exactly as tall as the screen it's showing.
        outer.setSizeConstraint(QLayout.SetFixedSize)

        top = QHBoxLayout()
        top.addWidget(_Mark(), 0, Qt.AlignLeft | Qt.AlignTop)
        top.addStretch(1)
        self._close = _btn("×", "close", QFont.Weight.Normal, 18)
        self._close.setFixedSize(30, 30)
        self._close.setToolTip("Close (Esc)")
        self._close.clicked.connect(self._dismiss)
        top.addWidget(self._close, 0, Qt.AlignTop)
        outer.addLayout(top)
        outer.addSpacing(18)

        self.stack = _Pages()
        self.stack.setFixedWidth(self.WIDTH - 68)
        outer.addWidget(self.stack)

        from account import config as account_config
        providers = account_config.oauth_providers()
        self.p_sign_in = self._build_sign_in(providers)
        self.p_create = self._build_create(providers)
        self.p_code = self._build_code()
        self.p_forgot = self._build_forgot()
        self.p_new_password = self._build_new_password()
        self.p_change_email = self._build_change_email()
        self.p_change_password = self._build_change_password()
        self.p_browser = self._build_browser()
        self.p_done = self._build_done()
        for page in (self.p_sign_in, self.p_create, self.p_code, self.p_forgot,
                     self.p_new_password, self.p_change_email, self.p_change_password,
                     self.p_browser, self.p_done):
            self.stack.addWidget(page)

    # ── pages ────────────────────────────────────────────────────────────
    def _providers_block(self, page: _Page, providers: list[str]) -> None:
        if "google" not in providers:
            return
        g = _btn("Continue with Google", "provider", QFont.Weight.Medium)
        row = QHBoxLayout(g)
        row.setContentsMargins(16, 0, 0, 0)
        row.addWidget(_GoogleMark(), 0, Qt.AlignVCenter | Qt.AlignLeft)
        row.addStretch(1)
        g.clicked.connect(lambda: self._start_provider("google"))
        page.add(g)
        or_row = QHBoxLayout()
        or_row.setContentsMargins(0, 4, 0, 4)
        for side in (0, 1):
            line = QWidget()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background:{style.HAIRLINE};")
            or_row.addWidget(line, 1, Qt.AlignVCenter)
            if side == 0:
                or_row.addWidget(_lbl("or", style.CAPTION, style.INK_MUTE), 0, Qt.AlignVCenter)
        page.col.addLayout(or_row)

    def _build_sign_in(self, providers: list[str]) -> _Page:
        lead = ("Your name and photo, on every computer you use Mike on. "
                "Your conversations still stay on this one.")
        page = _Page("Sign in to Mike", lead)
        self._providers_block(page, providers)
        self.si_email = page.add(_field("Email"))
        self.si_password = page.add(_field("Password", password=True))
        page.add_error()
        self.si_go = page.add(_btn("Sign in", "primary"))
        self.si_go.clicked.connect(self._sign_in)
        links = QHBoxLayout()
        forgot = _btn("Forgot password?", "link", QFont.Weight.Normal, style.SMALL)
        forgot.clicked.connect(lambda: self._go(self.p_forgot, email=self.si_email.text()))
        code = _btn("Email me a code instead", "link", QFont.Weight.Normal, style.SMALL)
        code.clicked.connect(self._sign_in_by_code)
        links.addWidget(forgot)
        links.addStretch(1)
        links.addWidget(code)
        page.col.addLayout(links)
        page.col.addSpacing(8)
        page.col.addLayout(self._footer("New to Mike?", "Create an account",
                                        lambda: self._go(self.p_create,
                                                         email=self.si_email.text())))
        for f in (self.si_email, self.si_password):
            f.returnPressed.connect(self._sign_in)
        return page

    def _build_create(self, providers: list[str]) -> _Page:
        page = _Page("Create your Mike account",
                     "Just who you are — your email, your name and, if you like, a photo.")
        self._providers_block(page, providers)
        self.cr_name = page.add(_field("Your name"))
        self.cr_email = page.add(_field("Email"))
        self.cr_password = page.add(_field("Password — at least 8 characters", password=True))
        page.add_error()
        self.cr_go = page.add(_btn("Create account", "primary"))
        self.cr_go.clicked.connect(self._create)
        link = (f'<a href="{{0}}" style="color:{style.INK_SOFT};text-decoration:underline;">'
                f'{{1}}</a>')
        legal = _lbl("By creating an account you agree to the "
                     f"{link.format('terms', 'Terms of Use')} and "
                     f"{link.format('privacy', 'Privacy Policy')}.",
                     style.CAPTION, style.INK_MUTE, rich=True)
        legal.linkActivated.connect(self._open_doc)
        page.add(legal)
        page.col.addSpacing(4)
        page.col.addLayout(self._footer("Already have an account?", "Sign in",
                                        lambda: self._go(self.p_sign_in,
                                                         email=self.cr_email.text())))
        for f in (self.cr_name, self.cr_email, self.cr_password):
            f.returnPressed.connect(self._create)
        return page

    def _build_code(self) -> _Page:
        page = _Page("Check your email", "")
        self.code = QLineEdit()
        self.code.setObjectName("code")
        self.code.setMaxLength(10)
        self.code.setAlignment(Qt.AlignCenter)
        f = style.font(24, QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        self.code.setFont(f)
        self.code.setPlaceholderText("000000")
        self.code.textEdited.connect(self._code_edited)
        self.code.returnPressed.connect(self._submit_code)
        page.add(self.code)
        page.add_error()
        self.code_go = page.add(_btn("Continue", "primary"))
        self.code_go.clicked.connect(self._submit_code)
        row = QHBoxLayout()
        self.resend = _btn("Resend code", "link", QFont.Weight.Normal, style.SMALL)
        self.resend.clicked.connect(self._resend_code)
        self.code_back = _btn("Use a different email", "link", QFont.Weight.Normal, style.SMALL)
        self.code_back.clicked.connect(self._code_back)
        row.addWidget(self.resend)
        row.addStretch(1)
        row.addWidget(self.code_back)
        page.col.addLayout(row)
        tip = _lbl("Can't find it? Check your spam folder. The code works for an hour.",
                   style.CAPTION, style.INK_MUTE)
        page.add(tip)
        return page

    def _build_forgot(self) -> _Page:
        page = _Page("Reset your password",
                     "We'll email you a code. Enter it here, then choose a new password.")
        self.fg_email = page.add(_field("Email"))
        page.add_error()
        self.fg_go = page.add(_btn("Send code", "primary"))
        self.fg_go.clicked.connect(self._forgot)
        self.fg_email.returnPressed.connect(self._forgot)
        page.col.addLayout(self._footer("Remembered it?", "Back to sign in",
                                        lambda: self._go(self.p_sign_in,
                                                         email=self.fg_email.text())))
        return page

    def _build_new_password(self) -> _Page:
        page = _Page("Choose a new password", "At least 8 characters.")
        self.np_password = page.add(_field("New password", password=True))
        self.np_confirm = page.add(_field("Type it again", password=True))
        page.add_error()
        self.np_go = page.add(_btn("Save password", "primary"))
        self.np_go.clicked.connect(self._save_new_password)
        for f in (self.np_password, self.np_confirm):
            f.returnPressed.connect(self._save_new_password)
        return page

    def _build_change_email(self) -> _Page:
        current = self.mgr.email()
        page = _Page("Change your email",
                     f"You sign in with <b>{current}</b>. We'll send a code to the new "
                     "address to confirm it's yours." if current else "")
        self.ce_email = page.add(_field("New email"))
        page.add_error()
        self.ce_go = page.add(_btn("Send code", "primary"))
        self.ce_go.clicked.connect(self._change_email)
        self.ce_email.returnPressed.connect(self._change_email)
        return page

    def _build_change_password(self) -> _Page:
        has = self.mgr.has_password()
        page = _Page("Change your password" if has else "Set a password",
                     "At least 8 characters." if has else
                     "Then you can also sign in with your email and this password.")
        self.cp_password = page.add(_field("New password", password=True))
        self.cp_confirm = page.add(_field("Type it again", password=True))
        page.add_error()
        self.cp_go = page.add(_btn("Save password", "primary"))
        self.cp_go.clicked.connect(self._change_password)
        for f in (self.cp_password, self.cp_confirm):
            f.returnPressed.connect(self._change_password)
        return page

    def _build_browser(self) -> _Page:
        page = _Page("Continue in your browser",
                     "Finish signing in in the browser window that just opened. "
                     "Mike is waiting for you here.")
        again = page.add(_btn("Open the page again", "provider", QFont.Weight.Medium))
        again.clicked.connect(self._reopen_provider)
        page.add_error()
        cancel = _btn("Cancel", "link", QFont.Weight.Normal, style.SMALL)
        cancel.clicked.connect(self._cancel_provider)
        page.add(cancel)
        self._provider_url = ""
        return page

    def _build_done(self) -> _Page:
        page = _Page("Done", "")
        go = page.add(_btn("Done", "primary"))
        go.clicked.connect(self.accept)
        return page

    def _footer(self, text: str, action: str, fn) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch(1)
        row.addWidget(_lbl(text, style.SMALL, style.INK_MUTE), 0, Qt.AlignVCenter)
        b = _btn(action, "accentlink", QFont.Weight.DemiBold, style.SMALL)
        b.clicked.connect(fn)
        row.addWidget(b, 0, Qt.AlignVCenter)
        row.addStretch(1)
        if self.first_run or self.required:
            skip_row = QVBoxLayout()
            skip_row.setSpacing(2)
            skip_row.addLayout(row)
            skip = _btn("Quit Mike" if self.required else "Continue without an account",
                        "link", QFont.Weight.Normal, style.SMALL)
            skip.clicked.connect(self._skip)
            wrap = QHBoxLayout()
            wrap.addStretch(1)
            wrap.addWidget(skip)
            wrap.addStretch(1)
            skip_row.addLayout(wrap)
            outer = QHBoxLayout()
            outer.addLayout(skip_row, 1)
            return outer
        return row

    # ── navigation ───────────────────────────────────────────────────────
    def _go(self, page: _Page, email: str = "") -> None:
        for f in (getattr(self, n, None) for n in ("si_email", "cr_email", "fg_email")):
            if f is not None and email and not f.text():
                f.setText(email.strip())
        page.show_error("")
        self.stack.setCurrentWidget(page)
        self._close.setVisible(not self.required)
        first = next((w for w in page.findChildren(QLineEdit)
                      if w.isVisibleTo(page) and not w.text()), None)
        if first is not None:
            QTimer.singleShot(0, first.setFocus)

    def _page(self) -> _Page:
        return self.stack.currentWidget()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            if not self.required:
                self._dismiss()
            return
        super().keyPressEvent(e)

    def _dismiss(self) -> None:
        self.mgr.cancel_sign_in()
        if self.first_run:
            self.skipped.emit()
        self.reject()

    def _skip(self) -> None:
        self.mgr.cancel_sign_in()
        self.skipped.emit()
        self.reject()

    def _open_doc(self, key: str) -> None:
        from ui.workspace import legal_view
        legal_view.show(key, self)

    # ── busy / errors ────────────────────────────────────────────────────
    def _set_busy(self, button: QPushButton | None, text: str = "") -> None:
        self._busy = button is not None
        page = self._page()
        for w in page.findChildren(QLineEdit):
            w.setEnabled(not self._busy)
        for w in page.findChildren(QPushButton):
            w.setEnabled(not self._busy)
        if button is not None:
            button.setProperty("idle_text", button.text())
            button.setText(text)
        else:
            for w in page.findChildren(QPushButton):
                idle = w.property("idle_text")
                if idle:
                    w.setText(idle)
                    w.setProperty("idle_text", None)
        if not self._busy and page is self.p_code:
            self._tick_resend(update_only=True)

    def _fail(self, e) -> None:
        self._set_busy(None)
        page = self._page()
        page.show_error(e.message)

    def _check_email(self, field: QLineEdit) -> str | None:
        email = field.text().strip()
        if not _EMAIL.match(email):
            self._page().show_error("Enter a valid email address.")
            field.setFocus()
            return None
        return email

    def _check_password(self, field: QLineEdit, confirm: QLineEdit | None = None) -> str | None:
        pw = field.text()
        if len(pw) < 8:
            self._page().show_error("Use at least 8 characters.")
            field.setFocus()
            return None
        if confirm is not None and confirm.text() != pw:
            self._page().show_error("Those passwords don't match.")
            confirm.setFocus()
            return None
        return pw

    # ── flows ────────────────────────────────────────────────────────────
    def _sign_in(self) -> None:
        if self._busy:
            return
        email = self._check_email(self.si_email)
        if not email:
            return
        if not self.si_password.text():
            self.p_sign_in.show_error("Enter your password — or get a code by email instead.")
            self.si_password.setFocus()
            return
        self._set_busy(self.si_go, "Signing in…")

        def failed(e):
            if e.code == "email_not_confirmed":
                self._set_busy(None)
                self.mgr.resend_signup(email)
                self._to_code(email, "email", resend="signup",
                              lead=f"Confirm your email first: we sent a code to <b>{email}</b>.")
                return
            self._fail(e)
        self.mgr.sign_in(email, self.si_password.text(), ok=self._signed_in, err=failed)

    def _sign_in_by_code(self) -> None:
        if self._busy:
            return
        email = self._check_email(self.si_email)
        if not email:
            return
        self._set_busy(self.si_go, "Sending…")
        self.mgr.send_code(email, ok=lambda: (self._set_busy(None),
                                              self._to_code(email, "email", resend="code")),
                           err=self._fail)

    def _create(self) -> None:
        if self._busy:
            return
        name = self.cr_name.text().strip()
        if not name:
            self.p_create.show_error("What should Mike call you?")
            self.cr_name.setFocus()
            return
        email = self._check_email(self.cr_email)
        if not email:
            return
        pw = self._check_password(self.cr_password)
        if not pw:
            return
        self._set_busy(self.cr_go, "Creating your account…")

        def done(state):
            self._set_busy(None)
            if state == "signed_in":
                self._signed_in()
            else:
                self._to_code(email, "email", resend="signup")
        self.mgr.sign_up(email, pw, name, ok=done, err=self._fail)

    def _forgot(self) -> None:
        if self._busy:
            return
        email = self._check_email(self.fg_email)
        if not email:
            return
        self._set_busy(self.fg_go, "Sending…")
        self.mgr.send_recovery(email, ok=lambda: (self._set_busy(None),
                                                  self._to_code(email, "recovery",
                                                                resend="recovery")),
                               err=self._fail)

    def _save_new_password(self) -> None:
        if self._busy:
            return
        pw = self._check_password(self.np_password, self.np_confirm)
        if not pw:
            return
        self._set_busy(self.np_go, "Saving…")
        self.mgr.set_password(pw, ok=self._signed_in, err=self._fail)

    def _change_email(self) -> None:
        if self._busy:
            return
        email = self._check_email(self.ce_email)
        if not email:
            return
        if email.lower() == self.mgr.email().lower():
            self.p_change_email.show_error("That's already the email you sign in with.")
            return
        self._set_busy(self.ce_go, "Sending…")
        self.mgr.change_email(email, ok=lambda: (self._set_busy(None),
                                                 self._to_code(email, "email_change",
                                                               resend="email_change")),
                              err=self._fail)

    def _change_password(self, nonce: str | None = None) -> None:
        if self._busy:
            return
        pw = self._pending_password if nonce else self._check_password(self.cp_password,
                                                                       self.cp_confirm)
        if not pw:
            return
        self._pending_password = pw
        if nonce is None:
            self._set_busy(self.cp_go, "Saving…")

        def failed(e):
            if e.code == "reauthentication_needed":
                self._set_busy(None)
                self.mgr.request_reauthentication(
                    ok=lambda: self._to_code(self.mgr.email(), "reauth", resend="reauth",
                                             lead="To confirm it's you, we sent a code to "
                                                  f"<b>{self.mgr.email()}</b>."),
                    err=self._fail)
                return
            self._fail(e)
        self.mgr.set_password(pw, nonce=nonce,
                              ok=lambda: self._finish("Password saved.",
                                                      "Use it next time you sign in."),
                              err=failed)

    # ── the code screen ──────────────────────────────────────────────────
    def _to_code(self, email: str, kind: str, resend: str, lead: str = "") -> None:
        self._code_ctx = {"email": email, "kind": kind, "resend": resend,
                          "from": self._page()}
        self.p_code.lead.setText(lead or f"We sent a 6-digit code to <b>{email}</b>.")
        self.p_code.lead.show()
        self.code.clear()
        self.code_back.setText("Use a different email" if kind in ("email", "recovery")
                               else "Back")
        self._start_resend_countdown()
        self._go(self.p_code)

    def _code_edited(self, text: str) -> None:
        digits = re.sub(r"\D", "", text)
        if digits != text:
            self.code.setText(digits)
        if len(digits) == 6:
            QTimer.singleShot(120, self._submit_code)

    def _submit_code(self) -> None:
        if self._busy:
            return
        code = re.sub(r"\D", "", self.code.text())
        if len(code) < 6:
            self.p_code.show_error("Enter the 6-digit code from the email.")
            return
        ctx = self._code_ctx
        kind = ctx.get("kind")
        self._set_busy(self.code_go, "Checking…")
        if kind == "email":
            self.mgr.verify_code(ctx["email"], code, "email", ok=self._signed_in,
                                 err=self._code_failed)
        elif kind == "recovery":
            self.mgr.verify_code(ctx["email"], code, "recovery",
                                 ok=lambda: (self._set_busy(None), self._go(self.p_new_password)),
                                 err=self._code_failed)
        elif kind == "email_change":
            def changed(complete):
                self._set_busy(None)
                if complete:
                    self._finish("Email changed.",
                                 f"You now sign in with <b>{self.mgr.email()}</b>.")
                else:
                    current = self.mgr.email()
                    self._code_ctx = {**ctx, "email": current, "resend": "email_change"}
                    self.p_code.lead.setText(
                        "One more: to make sure it's really you, we also sent a code to "
                        f"your current address, <b>{current}</b>.")
                    self.code.clear()
                    self.code.setFocus()
            self.mgr.confirm_email_change(ctx["email"], code, ok=changed, err=self._code_failed)
        elif kind == "reauth":
            self._set_busy(None)
            self._change_password(nonce=code)

    def _code_failed(self, e) -> None:
        self._fail(e)
        self.code.selectAll()
        self.code.setFocus()

    def _code_back(self) -> None:
        self._resend_timer.stop()
        self._go(self._code_ctx.get("from") or self.p_sign_in)

    def _start_resend_countdown(self) -> None:
        self._resend_left = RESEND_SECONDS
        self._resend_timer.start(1000)
        self._tick_resend(update_only=True)

    def _tick_resend(self, update_only: bool = False) -> None:
        if not update_only:
            self._resend_left = max(0, self._resend_left - 1)
        if self._resend_left:
            self.resend.setText(f"Resend code in {self._resend_left}s")
            self.resend.setEnabled(False)
        else:
            self._resend_timer.stop()
            self.resend.setText("Resend code")
            self.resend.setEnabled(not self._busy)

    def _resend_code(self) -> None:
        ctx = self._code_ctx
        email, how = ctx.get("email", ""), ctx.get("resend")
        done = lambda: (self._start_resend_countdown(),  # noqa: E731
                        self.p_code.show_error(""))

        def failed(e):
            if e.retry_after:
                self._resend_left = e.retry_after
                self._resend_timer.start(1000)
            self.p_code.show_error(e.message)
        if how == "signup":
            self.mgr.resend_signup(email, ok=done, err=failed)
        elif how == "code":
            self.mgr.send_code(email, ok=done, err=failed)
        elif how == "recovery":
            self.mgr.send_recovery(email, ok=done, err=failed)
        elif how == "email_change":
            self.mgr.change_email(self.ce_email.text().strip() or email, ok=done, err=failed)
        elif how == "reauth":
            self.mgr.request_reauthentication(ok=done, err=failed)
        self.resend.setEnabled(False)

    # ── Google ───────────────────────────────────────────────────────────
    def _start_provider(self, provider: str) -> None:
        if self._busy:
            return
        self._provider_from = self._page()
        self._go(self.p_browser)

        def failed(e):
            self._go(self._provider_from)
            self._provider_from.show_error(e.message)
        try:
            self._provider_url = self.mgr.sign_in_with(provider, ok=self._signed_in, err=failed)
        except Exception:
            from account.client import AccountError
            from logs.logger import logger
            logger.exception("Could not start %s sign-in.", provider)
            failed(AccountError("Couldn't start signing in. Try again."))

    def _reopen_provider(self) -> None:
        if self._provider_url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self._provider_url))

    def _cancel_provider(self) -> None:
        self.mgr.cancel_sign_in()
        self._go(getattr(self, "_provider_from", None) or self.p_sign_in)

    # ── finishing ────────────────────────────────────────────────────────
    def _signed_in(self) -> None:
        self._set_busy(None)
        self._resend_timer.stop()
        self.accept()

    def _finish(self, title: str, lead: str) -> None:
        self._set_busy(None)
        self._resend_timer.stop()
        self.p_done.title.setText(title)
        self.p_done.lead.setText(lead)
        self.p_done.lead.show()
        self._go(self.p_done)

    def done(self, result: int) -> None:  # noqa: D401 — Qt override
        self._resend_timer.stop()
        super().done(result)


def ask(parent=None, mode: str = "sign_in", *, first_run: bool = False,
        required: bool = False) -> bool:
    """Open the card and wait. True if it finished what it was opened for."""
    dlg = AuthDialog(mode, parent, first_run=first_run, required=required)
    if parent is not None and parent.isVisible():
        g = parent.frameGeometry()
        dlg.adjustSize()
        dlg.move(g.center().x() - dlg.width() // 2, g.center().y() - dlg.height() // 2 - 20)
    return dlg.exec() == QDialog.Accepted
