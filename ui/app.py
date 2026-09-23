from __future__ import annotations

import os
import platform
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


def _app_icon() -> QIcon:
    """Mike's real mark — the same rounded-square glyph served as
    huddlecode.com's own favicon — used wherever Windows needs a *file*
    icon rather than something QPainter can draw on demand: the taskbar
    entry, Alt+Tab, the window's title-bar corner. The PyInstaller build
    already bakes packaging/icon.ico into the .exe's own resources (so
    Explorer and the taskbar have it before Qt ever paints a frame); this
    loads the same file for Qt's own icon calls, checking next to the
    frozen executable first and falling back to the source tree so this
    also works from `python main.py` during development.
    """
    candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "packaging", "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "packaging", "icon.ico"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packaging", "icon.ico"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return QIcon(path)
    return QIcon()


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

        # The bridge is only half the editor integration; the other half is
        # an extension inside VS Code, which a user who downloaded a zip has
        # no way to know about. Offered once, in the background so a slow
        # `code --install-extension` can never delay the window appearing.
        _optional("the VS Code extension", self._offer_vscode_extension)

        self._build_tray()
        self._torn_down = False
        self._quitting = False

        # Ambient signal: when something happens while the panel is hidden,
        # the tray icon alone isn't enough. A native notification is the
        # macOS-native, unmistakable way to say "Mike needs you" or "Mike
        # finished" without stealing focus from what you were doing.
        self.page.state_changed.connect(self._ambient_signal)

        self.page.dismiss_requested.connect(self._animate_out)

        self.controller.startup()

    _AMBIENT = {
        "needs_user": ("Mike needs you", "There's a decision waiting."),
        "error": ("Mike stopped", "Something needs a look."),
        "done": ("Mike finished", "The task is done."),
    }

    def _ambient_signal(self, state: str) -> None:
        # Only when Mike is out of sight — if the panel is up, the state is
        # already visible on it.
        if state not in self._AMBIENT:
            return
        if self.isVisible() and not self.isMinimized():
            return
        title, body = self._AMBIENT[state]
        try:
            self.tray.showMessage(title, body, _tray_icon(), 4000)
        except Exception:
            logger.debug("Could not post ambient notification.", exc_info=True)

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

    def _offer_vscode_extension(self) -> bool:
        """Put Mike's editor extension in place, off the startup path.

        In a thread because `code --install-extension` shells out to Node and
        takes seconds; nothing about it should stand between the user and a
        window. Once per machine, and silent when VS Code isn't installed --
        which is the common case, not a failure.
        """
        import threading

        def _run() -> None:
            try:
                from ide.install import ensure_installed
                changed, reason = ensure_installed()
                if changed:
                    logger.info("VS Code extension: %s", reason)
            except Exception:
                logger.debug("VS Code extension check failed.", exc_info=True)

        threading.Thread(target=_run, name="vscode-extension", daemon=True).start()
        return True

    def _summon_after_tour(self) -> None:
        """Hand the user straight to the panel, focused and ready to type.

        The tour ends on "Start using Mike", so ending it anywhere other
        than in front of a cursor would be a dead end.
        """
        self.show()
        self.raise_()
        self.activateWindow()
        self.page.input.focus()
        self._tour = None

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

        # QKeySequence.Quit resolves to the platform's real quit shortcut on
        # macOS (Cmd+Q) -- but on Windows it resolves to "Exit", a physical
        # key that exists on essentially no real keyboard, verified directly
        # (QKeySequence(QKeySequence.Quit).toString() == "Exit", not
        # "Ctrl+Q"). Found because it left the tray icon's "Quit Mike" as
        # the *only* working way to close the app, and Windows commonly
        # collapses a new app's tray icon behind the notification area's
        # overflow arrow -- a real user had no way to quit at all. Ctrl+Q is
        # bound explicitly on Windows/Linux, matching what quits a browser,
        # Slack, or VS Code; macOS keeps the platform-native binding.
        QShortcut(
            QKeySequence.Quit if platform.system() == "Darwin" else QKeySequence("Ctrl+Q"),
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

    def _stop_summon_animations(self) -> None:
        """Stop whatever summon/dismiss animation is still in flight.

        _summon() toggles on every hotkey press, and nothing stops the user
        from pressing it again before the ~150-180ms show/hide animation has
        finished. Left alone, the old QPropertyAnimation is simply dropped in
        favour of a new one *while still running* — two animations then drive
        the same windowOpacity (and, for a show cut short by a hide, `pos`)
        property at once, and the abandoned one's `finished` signal still
        fires later and can act on a window that has since changed state
        (e.g. a stale fadeout hiding a window a following animate_in just
        showed). Stopping the previous animation before replacing it is the
        same guard `_teardown` already applies at shutdown, just applied on
        every toggle instead of only the last one.
        """
        for name in ("_fade", "_rise", "_fadeout"):
            anim = getattr(self, name, None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

    def _animate_in(self) -> None:
        """Mike appears — a fast fade and a small rise into place, so it reads
        as a presence arriving rather than a window opening. Short enough
        (~150ms) that it never feels like waiting."""
        self._stop_summon_animations()

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
        self._stop_summon_animations()

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
        self._stop_summon_animations()

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


def _maybe_show_welcome(window) -> None:
    """The first-install tour, shown exactly once per machine.

    Held on the window so Python doesn't collect it while it's on screen --
    a frameless top-level with no parent is otherwise only referenced by the
    local that created it, and it would vanish mid-animation.

    The flag is written when it opens, not when it finishes: someone who
    closes it immediately has still been offered it, and a tour that
    reappears because you dismissed it is worse than no tour at all.
    """
    from config import preferences

    if preferences.get("welcome_tour_shown", False):
        return
    try:
        from ui.welcome import WelcomeWindow

        preferences.set_value("welcome_tour_shown", True)
        tour = WelcomeWindow()
        window._tour = tour

        screen = QApplication.primaryScreen().availableGeometry()
        tour.move(screen.center().x() - tour.width() // 2,
                  screen.center().y() - tour.height() // 2 - 30)
        tour.finished.connect(window._summon_after_tour)
        tour.show()
        tour.raise_()
        tour.activateWindow()
    except Exception:
        logger.exception("The welcome tour could not open; Mike continues without it.")


def run():

    app = QApplication(sys.argv)

    app.setApplicationName("Mike")

    app.setWindowIcon(_app_icon())

    app.setStyleSheet(GLOBAL_STYLESHEET)

    # Mike's whole premise is that he's still there after the window closes
    # (hotkey, wake word, IDE bridge, Edge). Without this, Qt quits the
    # entire app the moment the last window closes — which is exactly the
    # contradiction being fixed here. The tray's "Quit Mike" and Cmd+Q are
    # the only real quit paths now (see MikeWindow._request_quit).
    app.setQuitOnLastWindowClosed(False)

    window = MikeWindow()

    # The one-time tour. Gated on its own preference rather than
    # onboarding_complete, so the two can never be confused: the panel's
    # starter chips are "try something now", this is "what is this and why
    # is it on my computer". Shown once per machine, before the panel is
    # touched, and skippable from the first card.
    _maybe_show_welcome(window)

    # The one real shutdown path — fires on every genuine quit (tray Quit,
    # Cmd+Q, or any other route to QApplication.quit()) regardless of which
    # one triggered it, and never fires from just closing the window.
    app.aboutToQuit.connect(window._teardown)

    # Not while the tour is up. Both are always-on-top frameless windows, so
    # showing the panel here put it straight through the middle of the
    # welcome card -- two surfaces fighting for the same pixels on the one
    # screen that is supposed to explain the product. The tour hands over to
    # the panel itself when it closes (_summon_after_tour).
    if getattr(window, "_tour", None) is None:
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
