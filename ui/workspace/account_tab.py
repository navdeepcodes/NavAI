"""Settings → Account: who you're signed in as, and everything about it.

Signed out, it says what an account is for — and what it never holds.
Signed in: your photo and name (the name Mike calls you), how you sign in,
signing out of this computer, and deleting the account.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout

from ui.panel import style
from ui.workspace.avatar import Avatar
from ui.workspace.pages import (
    _arm, _button, _card, _group, _label, _row, _rows_card, _Tab,
)


class AccountTab(_Tab):

    def __init__(self, hooks: dict | None = None, parent=None) -> None:
        from account.manager import manager
        self._hooks = hooks or {}
        self.mgr = manager()
        super().__init__(parent)
        self.mgr.changed.connect(self._on_changed)

    def _on_changed(self) -> None:
        # Don't rebuild under someone typing their name.
        name = getattr(self, "_name", None)
        if name is not None and name.hasFocus():
            return
        self.reload()

    def build(self) -> None:
        if self.mgr.signed_in():
            self._build_signed_in()
        else:
            self._build_signed_out()
        self.body.addStretch(1)

    # ── signed out ───────────────────────────────────────────────────────
    def _build_signed_out(self) -> None:
        card, col = _card()
        col.setContentsMargins(24, 24, 24, 24)
        col.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(Avatar(56), 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(_label("Sign in to Mike", style.TITLE, style.INK, QFont.Weight.DemiBold))
        text.addWidget(_label(
            "Keep your name and photo with you on every computer you use Mike on.",
            style.BODY, style.INK_SOFT))
        top.addLayout(text, 1)
        col.addLayout(top)
        col.addSpacing(10)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        create = _button("Create account")
        create.clicked.connect(lambda: self._open("create"))
        buttons.addWidget(create)
        sign_in = _button("Sign in", "pill")
        sign_in.setFont(style.font(style.SMALL, QFont.Weight.DemiBold))
        sign_in.clicked.connect(lambda: self._open("sign_in"))
        buttons.addWidget(sign_in)
        col.addLayout(buttons)
        self.add(card)

        from account import config as account_config
        rows = [
            _row("Your email, name and photo",
                 "So Mike knows you on any computer. Stored with Supabase, our "
                 "account provider."),
            _row("Never your conversations",
                 "Chats, memory, files and activity stay on this computer, "
                 "signed in or not."),
        ]
        if not account_config.required():
            rows.append(_row("Optional", "Everything in Mike works without an account."))
        self.add(_group("What an account holds"))
        self.add(_rows_card(rows))

    # ── signed in ────────────────────────────────────────────────────────
    def _build_signed_in(self) -> None:
        m = self.mgr
        if m.offline:
            banner = _label("You're offline. Mike is showing what's saved on this computer; "
                            "changes to your account need a connection.",
                            style.SMALL, style.INK_SOFT)
            banner.setContentsMargins(4, 0, 4, 4)
            self.add(banner)

        card, col = _card()
        col.setContentsMargins(24, 22, 24, 22)
        col.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(18)
        self._avatar = Avatar(72)
        self._avatar.setCursor(Qt.PointingHandCursor)
        self._avatar.setToolTip("Change your photo")
        self._avatar.clicked.connect(self._pick_photo)
        top.addWidget(self._avatar, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(_label("Name", style.SMALL, style.INK_SOFT, QFont.Weight.Medium))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self._name = QLineEdit(m.display_name())
        self._name.setObjectName("field")
        self._name.setFont(style.font(style.BODY))
        self._name.setPlaceholderText("What should Mike call you?")
        self._name.setMaxLength(80)
        self._name.returnPressed.connect(self._save_name)
        name_row.addWidget(self._name, 1)
        self._save = _button("Save", "pill")
        self._save.clicked.connect(self._save_name)
        name_row.addWidget(self._save)
        text.addLayout(name_row)
        self._status = _label(m.email(), style.SMALL, style.INK_MUTE)
        text.addWidget(self._status)
        photo_row = QHBoxLayout()
        photo_row.setContentsMargins(0, 4, 0, 0)
        photo_row.setSpacing(8)
        change = _button("Change photo…")
        change.clicked.connect(self._pick_photo)
        photo_row.addWidget(change)
        if m.profile.get("avatar_path"):
            remove = _button("Remove photo")
            remove.clicked.connect(self._remove_photo)
            photo_row.addWidget(remove)
        photo_row.addStretch(1)
        text.addLayout(photo_row)
        top.addLayout(text, 1)
        col.addLayout(top)
        self.add(card)

        self.add(_group("Signing in"))
        email_desc = m.email()
        if m.pending_email():
            email_desc += f" · waiting for you to confirm {m.pending_email()}"
        change_email = _button("Change…")
        change_email.clicked.connect(lambda: self._open("change_email"))
        pw = _button("Change…" if m.has_password() else "Set…")
        pw.clicked.connect(lambda: self._open("change_password"))
        rows = [
            _row("Email", email_desc, change_email),
            _row("Password",
                 "The password you sign in with." if m.has_password() else
                 "Set one to sign in with your email as well.", pw),
        ]
        if "google" in m.providers():
            rows.append(_row("Google", "You can sign in with your Google account."))
        self.add(_rows_card(rows))

        self.add(_group("This computer"))
        out = _button("Sign out")
        out.clicked.connect(self._sign_out)
        self.add(_rows_card([
            _row("Sign out", "Your conversations, memory and settings stay on this computer.",
                 out),
        ]))

        self.add(_group("Delete account"))
        delete = _button("Delete account…")
        _arm(delete, "Delete account?", self._delete)
        self.add(_rows_card([
            _row("Delete your Mike account",
                 "Permanently deletes your account, name and photo from Mike's servers. "
                 "What's on this computer isn't touched.", delete),
        ]))

    # ── actions ──────────────────────────────────────────────────────────
    def _open(self, mode: str) -> None:
        from ui.workspace import account_dialog
        account_dialog.ask(self.window(), mode)
        self.reload()

    def _flash(self, text: str, colour: str = style.GOOD) -> None:
        status = getattr(self, "_status", None)
        if status is None:
            return
        status.setText(text)
        status.setStyleSheet(f"color:{colour};background:transparent;")

        def back():
            try:
                status.setText(self.mgr.email())
                status.setStyleSheet(f"color:{style.INK_MUTE};background:transparent;")
            except RuntimeError:
                pass  # rebuilt meanwhile
        QTimer.singleShot(2600, back)

    def _failed(self, e) -> None:
        self._save.setEnabled(True)
        self._flash(e.message, style.STOP)

    def _save_name(self) -> None:
        name = self._name.text().strip()
        if name == self.mgr.display_name():
            return
        self._save.setEnabled(False)
        from config import preferences
        preferences.set_value("profile_name", name)

        def done():
            self._save.setEnabled(True)
            self._name.clearFocus()
            self._flash("Saved")
            hook = self._hooks.get("profile_changed")
            if hook:
                hook()
        self.mgr.update_name(name, ok=done, err=self._failed)

    def _pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a photo", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        from account.client import AccountError
        from account.manager import avatar_png
        try:
            png = avatar_png(path)
        except AccountError as e:
            self._flash(e.message, style.STOP)
            return
        self._flash("Uploading your photo…", style.INK_MUTE)
        self.mgr.set_avatar(png, ok=lambda: self._flash("Photo updated"), err=self._failed)

    def _remove_photo(self) -> None:
        self.mgr.remove_avatar(ok=lambda: None, err=self._failed)

    def _sign_out(self) -> None:
        self.mgr.sign_out()

    def _delete(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Delete your Mike account?")
        box.setText("Delete your Mike account?")
        box.setInformativeText(
            f"This permanently deletes the account for {self.mgr.email()}, with its name "
            "and photo. It can't be undone.\n\nYour conversations, memory and files on "
            "this computer are not affected.")
        go = box.addButton("Delete account", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return

        def done():
            QMessageBox.information(self, "Account deleted",
                                    "Your Mike account has been deleted. Mike keeps working "
                                    "on this computer, without an account.")

        def failed(e):
            QMessageBox.warning(self, "Couldn't delete your account", e.message)
        self.mgr.delete_account(ok=done, err=failed)
