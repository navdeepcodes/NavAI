"""The installer window.

Built in Mike's own visual language (ui/panel/style.py) so the first thing
a user ever sees already looks like the product, rather than a generic
wizard with a grey 3D border.

The copy runs on a worker thread and reports through a signal. That is not
ceremony: copying ~1000 files takes several seconds, and doing it on the GUI
thread would freeze the window and grey the title bar -- the "not
responding" state that reads as a crash. Progress is real, taken from the
actual file count, never a fake animation.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from installer import core

# Mike's palette, restated rather than imported: the installer must keep
# working even if it is ever shipped without the full ui package.
PAPER = "#F7F7F8"
PAPER_DIM = "#EEEEF0"
INK = "#0E0E10"
GRAPHITE = "#525459"
MIST = "#DCDCE0"
ACCENT = "#AE6534"
GOOD = "#5F8D5A"
UI_FONT = "Segoe UI"


class _Worker(QThread):
    progress = Signal(int, str)
    done = Signal(bool, str)

    def __init__(self, wait_for: int | None = None) -> None:
        super().__init__()
        self._wait_for = wait_for

    def run(self) -> None:
        try:
            source = core.source_dir()
            if self._wait_for:
                # The Mike that started this update is quitting: let it finish.
                self.progress.emit(1, "Waiting for Mike to close…")
                core.wait_for_exit([self._wait_for], 60)
            if core.running_mike():
                self.progress.emit(2, "Closing Mike…")
                if not core.stop_running_mike():
                    raise RuntimeError("Mike is still running -- quit him from the tray and try again")
            self.progress.emit(2, "Preparing…")
            core.copy_tree(source, core.INSTALL_DIR, lambda p, m: self.progress.emit(p, m))
            self.progress.emit(97, "Adding Mike to your Start Menu…")
            core.make_shortcuts(core.INSTALL_DIR)
            self.progress.emit(100, "Done")
            self.done.emit(True, "")
        except Exception as exc:
            self.done.emit(False, str(exc))


class InstallerWindow(QWidget):
    SHADOW = 18

    def __init__(self, update_from: int | None = None) -> None:
        super().__init__()
        self._update_from = update_from
        self.setWindowTitle("Updating Mike" if update_from else "Install Mike")
        self.setFixedSize(520, 330)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self._worker: _Worker | None = None
        self._build()

    # ── look ────────────────────────────────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        body = QPainterPath()
        rect = self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)
        body.addRoundedRect(rect, 16, 16)
        for i in range(self.SHADOW, 0, -1):
            glow = QPainterPath()
            glow.addRoundedRect(
                self.rect().adjusted(self.SHADOW - i, self.SHADOW - i,
                                     -(self.SHADOW - i), -(self.SHADOW - i)),
                16 + i * 0.5, 16 + i * 0.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, max(1, int(8 - i * 0.35))))
            p.drawPath(glow)
        p.setBrush(QColor(PAPER))
        p.setPen(Qt.NoPen)
        p.drawPath(body)

    def _mark(self) -> QWidget:
        """Mike's own mark: the nib on its graphite tile, as on the app icon
        (three bars on ink if the app's drawing isn't available)."""
        class Mark(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.setFixedSize(46, 46)

            def paintEvent(self, _e) -> None:
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing, True)
                p.setPen(Qt.NoPen)
                try:
                    from PySide6.QtCore import QRectF
                    from ui.workspace import nib
                    p.setBrush(QColor("#1E1F23"))
                    p.drawRoundedRect(0, 0, 46, 46, 11, 11)
                    nib.paint_centred(p, QRectF(0, 0, 46, 46), QColor("#E3A46B"),
                                      QColor("#8A4E22"), scale=0.72)
                    return
                except Exception:
                    pass
                p.setBrush(QColor(INK))
                p.drawRoundedRect(0, 0, 46, 46, 9, 9)
                p.setBrush(QColor(PAPER))
                unit = 46 / 32
                for x, y, w, h in ((9, 13, 3, 6), (14.5, 8, 3, 16), (20, 11, 3, 10)):
                    p.drawRoundedRect(x * unit, y * unit, w * unit, h * unit,
                                      (w / 2) * unit, (w / 2) * unit)
        return Mark()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW + 26, self.SHADOW + 24,
                                 self.SHADOW + 26, self.SHADOW + 22)
        outer.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(self._mark(), 0, Qt.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Mike")
        title.setFont(QFont(UI_FONT, 19, QFont.DemiBold))
        title.setStyleSheet(f"color:{INK};background:transparent;")
        subtitle = QLabel("A personal assistant that lives on your PC.")
        subtitle.setFont(QFont(UI_FONT, 10))
        subtitle.setStyleSheet(f"color:{GRAPHITE};background:transparent;")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)
        outer.addLayout(head)
        outer.addSpacing(20)

        self._body = QLabel(
            "Mike runs entirely on this PC — your conversations never leave "
            "the machine.\n\nHe'll be added to your Start Menu, and you can "
            "call him any time with Ctrl+Shift+Space."
        )
        self._body.setWordWrap(True)
        self._body.setFont(QFont(UI_FONT, 10))
        self._body.setStyleSheet(f"color:{GRAPHITE};background:transparent;")
        outer.addWidget(self._body)
        outer.addStretch(1)

        self._status = QLabel("")
        self._status.setFont(QFont(UI_FONT, 9))
        self._status.setStyleSheet(f"color:{GRAPHITE};background:transparent;")
        outer.addWidget(self._status)
        outer.addSpacing(6)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(5)
        self._bar.setRange(0, 100)
        self._bar.hide()
        self._bar.setStyleSheet(
            f"QProgressBar{{background:{MIST};border:none;border-radius:3px;}}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:3px;}}"
        )
        outer.addWidget(self._bar)
        outer.addSpacing(14)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel = QPushButton("Not now")
        self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.setFont(QFont(UI_FONT, 10))
        self._cancel.setStyleSheet(
            f"QPushButton{{background:transparent;color:{GRAPHITE};border:none;padding:9px 14px;}}"
            f"QPushButton:hover{{color:{INK};}}"
        )
        self._cancel.clicked.connect(self.close)
        buttons.addWidget(self._cancel)

        self._go = QPushButton("Install Mike")
        self._go.setCursor(Qt.PointingHandCursor)
        self._go.setFont(QFont(UI_FONT, 10, QFont.DemiBold))
        self._go.setStyleSheet(
            f"QPushButton{{background:{INK};color:{PAPER};border:none;"
            f"border-radius:9px;padding:10px 20px;}}"
            f"QPushButton:hover{{background:{ACCENT};}}"
            f"QPushButton:disabled{{background:{MIST};color:{GRAPHITE};}}"
        )
        self._go.clicked.connect(self._install)
        buttons.addWidget(self._go)
        outer.addLayout(buttons)

        if self._update_from:
            try:
                from config.settings import VERSION
            except Exception:
                VERSION = "the newest version"
            self._body.setText(
                f"Mike is updating to {VERSION}.\n\nYour chats, memory and settings "
                "stay exactly as they are. He'll be back in a moment.")
            QTimer.singleShot(300, self._install)
        elif core.running_mike():
            self._body.setText(
                self._body.text() + "\n\nMike is running right now; installing "
                "closes him first. Your chats and settings are kept.")
            self._go.setText("Close Mike and install")

    # ── behaviour ───────────────────────────────────────────
    def _install(self) -> None:
        self._go.setEnabled(False)
        self._cancel.hide()
        self._bar.show()
        self._bar.setValue(0)
        self._status.setText("Preparing…")

        self._worker = _Worker(self._update_from)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, value: int, message: str) -> None:
        self._bar.setValue(value)
        self._status.setText(message)

    def _on_done(self, ok: bool, error: str) -> None:
        if not ok:
            self._status.setStyleSheet("color:#B4472F;background:transparent;")
            self._status.setText(f"Couldn't finish: {error[:90]}")
            if self._update_from and core.already_installed():
                # copy_tree keeps the old version when a swap fails: reopen it.
                self._body.setText("The update didn't finish, so your current version "
                                   "of Mike was kept. It's opening again now.")
                QTimer.singleShot(2500, self._launch_and_quit)
                return
            self._go.setText("Close")
            self._go.setEnabled(True)
            try:
                self._go.clicked.disconnect()
            except Exception:
                pass
            self._go.clicked.connect(self.close)
            return

        self._bar.hide()
        if self._update_from:
            self._body.setText("Mike is up to date. Starting him again…")
            self._status.setStyleSheet(f"color:{GOOD};background:transparent;")
            self._status.setText("Updated")
            QTimer.singleShot(900, self._launch_and_quit)
            return
        if core.ollama_present():
            self._body.setText(
                "Mike is installed.\n\nHe's in your Start Menu, and Ctrl+Shift+Space "
                "calls him from anywhere. Starting him now…"
            )
            self._status.setStyleSheet(f"color:{GOOD};background:transparent;")
            self._status.setText("Ready")
            QTimer.singleShot(1400, self._launch_and_quit)
        else:
            self._body.setText(
                "Mike is installed — one thing left.\n\nMike thinks using a model "
                "that runs on this PC, and Ollama is what runs it. Install it free "
                "from ollama.com/download, then open Mike from your Start Menu."
            )
            self._status.setStyleSheet(f"color:{GRAPHITE};background:transparent;")
            self._status.setText("Ollama isn't installed yet")
            self._go.setText("Get Ollama")
            self._go.setEnabled(True)
            try:
                self._go.clicked.disconnect()
            except Exception:
                pass
            self._go.clicked.connect(self._open_ollama)

    def _open_ollama(self) -> None:
        import os
        try:
            os.startfile("https://ollama.com/download")
        except Exception:
            pass
        self.close()

    def _launch_and_quit(self) -> None:
        import subprocess
        try:
            subprocess.Popen([str(core.INSTALL_DIR / "Mike.exe")], cwd=str(core.INSTALL_DIR))
        except Exception:
            pass
        QApplication.instance().quit()

    # Frameless windows have to move themselves.
    def mousePressEvent(self, event) -> None:
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if getattr(self, "_drag", None) and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)


def run_installer() -> int:
    global UI_FONT
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Install Mike")
    # The first thing someone sees after unzipping should already look like
    # Mike: his bundled face if it's there, Segoe UI if it isn't.
    try:
        from ui.panel import style as _style
        if _style.load_fonts():
            UI_FONT = _style.BRAND_FAMILY
    except Exception:
        pass
    update_from = None
    if "--update-from" in sys.argv:
        try:
            update_from = int(sys.argv[sys.argv.index("--update-from") + 1])
        except (IndexError, ValueError):
            update_from = 0
    window = InstallerWindow(update_from=update_from)
    screen = app.primaryScreen().availableGeometry()
    window.move(screen.center().x() - window.width() // 2,
                screen.center().y() - window.height() // 2 - 40)
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()
