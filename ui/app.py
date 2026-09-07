from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from brain.core_runtime import CoreRuntime

from ide import manager as ide_manager
from logs.logger import logger
from ui.controller.ui_controller import UIController
from ui.instrument import tokens
from ui.instrument.edge import EdgeStrip
from ui.system.global_hotkey import GlobalHotkey
from ui.panel.mike_panel import MikePanel
from ui.theme.stylesheet import GLOBAL_STYLESHEET
from ui.instrument.invoke import InvokeLine


def _tray_icon() -> QIcon:
    """
    A plain filled dot in Mike's own accent color — a menu-bar presence
    needs an icon, not a logo. Drawn in code rather than shipping an asset
    for one small dot.
    """
    size = 22
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(tokens.AMBER))
    painter.setPen(Qt.NoPen)
    margin = 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()
    return QIcon(pixmap)


def _optional(what: str, start) -> bool:
    """Start a background service that Mike can live without.

    These are conveniences: an editor bridge, a global hotkey, a tray icon.
    Each already handles the failure it expects — the bridge returns False
    when its port is taken — but an unexpected one propagated out of
    __init__ and stopped the window from opening at all. Losing the hotkey
    is an inconvenience; losing Mike because of the hotkey is not a trade
    worth making, so anything unexpected is logged and stepped over.

    Deliberately not used for the runtime, the controller or the page: those
    are Mike, and a window without them would be a shell pretending to work.
    """
    try:
        return bool(start())
    except Exception:
        logger.exception("Could not start %s; Mike continues without it.", what)
        return False


class MikeWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.runtime = CoreRuntime()

        # The settings surface edits real engines, so it is handed the
        # controller's own switches rather than its own copies of state.
        self._settings_hooks = {}
        self.page = MikePanel(self._settings_hooks)

        self.floating = InvokeLine()

        self.edge = EdgeStrip()

        self.controller = UIController(
            runtime=self.runtime,
            page=self.page,
            floating=self.floating,
            edge=self.edge,
        )

        self._settings_hooks["on_voice_toggle"] = self.controller.set_voice_enabled
        self._settings_hooks["on_wake_toggle"] = self.controller.set_wake_word_enabled

        self.setCentralWidget(self.page)

        self._configure_window()

        self._configure_shortcuts()

        self.floating.expand_requested.connect(self._expand_from_floating)

        self.edge.expand_requested.connect(self._summon)

        # Reachable from any application, not just when Mike has focus.
        self.hotkey = GlobalHotkey(self._summon)
        _optional("the global hotkey", self.hotkey.register)

        # Listen for an editor. Mike works exactly the same if none ever
        # connects, or if the port is already taken.
        _optional("the IDE bridge", ide_manager.start)

        self._build_tray()
        self._torn_down = False
        self._quitting = False

        self.controller.startup()

    def _build_tray(self) -> None:
        """
        The one honest signal that Mike is still here after the window
        closes — a menu-bar icon, not a promise in an onboarding sentence.
        Two items, on purpose: bring the window back, or actually leave.
        """
        # Parented and held on self on purpose: a bare local QMenu is only
        # referenced by the native status item, so Python is free to collect
        # it out from under Qt.
        self._tray_menu = QMenu(self)
        self._tray_menu.addAction("Show Mike", self._show_main_window)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction("Quit Mike", self._request_quit)

        self.tray = QSystemTrayIcon(_tray_icon(), self)
        self.tray.setToolTip("Mike")
        self.tray.setContextMenu(self._tray_menu)
        self.tray.show()

    def _show_main_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _request_quit(self) -> None:
        """
        The only path that actually ends Mike — closing the window no
        longer does this (see closeEvent). Routed through QApplication so
        aboutToQuit fires exactly once regardless of what triggered it.

        _quitting is set first and read by closeEvent: quitting asks every
        top-level window to close, and a window that ignores that request
        cancels the quit outright. Without this flag the close handler below
        would refuse, and "Quit Mike" could never actually quit.
        """
        self._quitting = True
        QApplication.instance().quit()

    PANEL_WIDTH = 620

    def _configure_window(self):
        # A summoned presence, not a window you live in: frameless, floating,
        # translucent so the panel's own rounded surface reads as a system
        # layer over whatever you were doing. Tool-window so it stays out of
        # the dock and app switcher -- Mike is reached by the hotkey, not by
        # hunting for a window. Height follows the panel's content; width is
        # fixed at a comfortable reading measure.
        self.setWindowTitle("Mike")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("QMainWindow { background: transparent; }")

        self.setFixedWidth(self.PANEL_WIDTH)
        self.setFixedHeight(self.page.desired_height())

        try:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.PANEL_WIDTH // 2, screen.top() + 130)
        except Exception:
            pass

    def _configure_shortcuts(self):

        QShortcut(
            QKeySequence("Ctrl+L"),
            self,
            activated=self.page.clear,
        )

        # QKeySequence.Quit resolves to the platform's real quit shortcut
        # (Cmd+Q on macOS). Bound explicitly rather than relying on Qt's
        # implicit default app menu, so it's unambiguous which path a real
        # quit takes.
        QShortcut(
            QKeySequence.Quit,
            self,
            activated=self._request_quit,
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F6:
            self.controller.voice_shortcut_pressed()
            return
        if event.key() == Qt.Key_Escape:
            # Escape backs out of an overlay first; only cancels real work
            # when the Home stage itself is what's showing.
            if self.page.showing_overlay():
                self.page.close_overlays()
            else:
                self.controller.cancel_active()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        # Mike is fully on screen; the ambient tick would be a duplicate.
        super().showEvent(event)
        self.edge.sleep()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.edge.wake()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.edge.wake()
            else:
                self.edge.sleep()

    def _summon(self) -> None:
        """Global invocation: bring Mike forward, or put him away again.

        The panel *is* the summoned presence -- a compact floating surface that
        the hotkey shows directly, rather than a separate quick-line that then
        expands into a heavier window. One coherent surface, summoned and
        dismissed by the same key, wherever the user is. The ambient edge
        strip remains Mike's "still here" mark while he's away.
        """
        self.edge.dismiss()

        if self.isVisible() and not self.isMinimized():
            self._animate_out()
            return

        self._animate_in()

    def _animate_in(self) -> None:
        """Mike appears — a fast fade and a small rise into place, so it reads
        as a presence arriving rather than a window opening. Short enough
        (~150ms) that it never feels like waiting."""
        try:
            screen = QApplication.primaryScreen().availableGeometry()
            rest_x = screen.center().x() - self.PANEL_WIDTH // 2
            rest_y = screen.top() + 130
        except Exception:
            rest_x, rest_y = self.x(), self.y()

        self.setWindowOpacity(0.0)
        self.move(rest_x, rest_y + 10)
        self.show()
        self.raise_()
        self.activateWindow()
        self.page.input.focus()

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

        self._rise = QPropertyAnimation(self, b"pos", self)
        self._rise.setDuration(180)
        self._rise.setStartValue(QPoint(rest_x, rest_y + 10))
        self._rise.setEndValue(QPoint(rest_x, rest_y))
        self._rise.setEasingCurve(QEasingCurve.OutCubic)

        self._fade.start()
        self._rise.start()

    def _animate_out(self) -> None:
        """Mike steps back — a quick fade, then actually hidden."""
        self._fadeout = QPropertyAnimation(self, b"windowOpacity", self)
        self._fadeout.setDuration(110)
        self._fadeout.setStartValue(self.windowOpacity())
        self._fadeout.setEndValue(0.0)
        self._fadeout.setEasingCurve(QEasingCurve.InCubic)
        self._fadeout.finished.connect(self._finish_hide)
        self._fadeout.start()

    def _finish_hide(self) -> None:
        self.hide()
        self.setWindowOpacity(1.0)

    def _expand_from_floating(self) -> None:
        self.floating.dismiss()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """
        Closing the window is not quitting Mike — it's putting the window
        away. The hotkey, wake word, IDE bridge, and Edge ambient presence
        all keep running, exactly as the onboarding text already promises.
        Real shutdown only ever happens through _request_quit (the tray's
        Quit item, or Cmd+Q), which sets _quitting first — during a genuine
        quit this must accept, or refusing here would cancel the quit and
        leave Mike running with no way to stop him.
        """
        if getattr(self, "_quitting", False):
            event.accept()
            return

        event.ignore()
        self.hide()

    def _teardown(self) -> None:
        """
        The one real shutdown path, reached only via a genuine quit
        (QApplication.aboutToQuit) — never from closing the window. Guarded
        so it only ever runs once regardless of how many quit signals fire.
        """
        if getattr(self, "_torn_down", False):
            return
        self._torn_down = True

        # Stop any in-flight summon/dismiss animations before the window goes,
        # so a property animation can never fire a frame against a window that
        # is being destroyed.
        for name in ("_fade", "_rise", "_fadeout"):
            anim = getattr(self, name, None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

        self.controller.shutdown()

        # Background processes Mike started (dev servers, watchers) are
        # detached and would outlive the app otherwise — quitting Mike should
        # not leave his servers running with nothing left to manage them.
        try:
            from tools.terminal.actions import shutdown_all
            shutdown_all()
        except Exception:
            logger.exception("Could not stop background processes.")

        ide_manager.stop()
        self.hotkey.unregister()
        self.tray.hide()
        self.edge.close()
        self.floating.close()


def run():

    app = QApplication(sys.argv)

    app.setApplicationName("Mike")

    app.setStyleSheet(GLOBAL_STYLESHEET)

    # Mike's whole premise is that he's still there after the window closes
    # (hotkey, wake word, IDE bridge, Edge). Without this, Qt quits the
    # entire app the moment the last window closes — which is exactly the
    # contradiction being fixed here. The tray's "Quit Mike" and Cmd+Q are
    # the only real quit paths now (see MikeWindow._request_quit).
    app.setQuitOnLastWindowClosed(False)

    window = MikeWindow()

    # The one real shutdown path — fires on every genuine quit (tray Quit,
    # Cmd+Q, or any other route to QApplication.quit()) regardless of which
    # one triggered it, and never fires from just closing the window.
    app.aboutToQuit.connect(window._teardown)

    window.show()

    code = app.exec()

    window._teardown()

    # A worker parked in a blocking model request can't be interrupted, so Qt
    # would abort destroying its thread. We're exiting anyway — leave without
    # running C++ destructors rather than crashing on the way out.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":

    run()
