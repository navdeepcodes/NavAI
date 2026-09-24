from __future__ import annotations

import os
import platform
import sys

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from brain.core_runtime import CoreRuntime

from ide import manager as ide_manager
from logs.logger import logger
from ui.controller.ui_controller import UIController
from ui.panel import style
from ui.system.global_hotkey import GlobalHotkey
from ui.workspace.workspace import MikeWorkspace
from ui.workspace.corner import CornerPresence
from ui.theme.stylesheet import GLOBAL_STYLESHEET


def _app_icon() -> QIcon:
    """Mike's real mark — the rounded-square glyph — for the taskbar entry,
    Alt+Tab, and the window's own icon. The frozen build bakes
    packaging/icon.ico into the .exe; this loads the same file for Qt's icon
    calls, next to the frozen executable first, then the source tree."""
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
    """The nib on its terracotta tile — the same mark as the taskbar, drawn
    at the tray's sizes rather than scaled down from the big icon."""
    from PySide6.QtCore import QRectF
    from ui.workspace import nib

    icon = QIcon()
    for size in (16, 20, 24, 32):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#C4602F"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        nib.paint_centred(painter, QRectF(0, 0, size, size), QColor("#F6EFE3"), scale=0.8)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def _optional(what: str, start) -> bool:
    """Start a background convenience Mike can live without, stepping over an
    unexpected failure rather than letting it stop the window opening."""
    try:
        return bool(start())
    except Exception:
        logger.exception("Could not start %s; Mike continues without it.", what)
        return False


class MikeWindow(QMainWindow):

    #: Opens as a real desktop application, not a tiny rectangle.
    DEFAULT_W = 1180
    DEFAULT_H = 760
    MIN_WIDTH = 860
    MIN_HEIGHT = 580

    def __init__(self):
        super().__init__()

        self.runtime = CoreRuntime()

        # The settings surface edits real engines, so it's handed the
        # controller's own switches rather than its own copies of state.
        self._settings_hooks = {}
        self.page = MikeWorkspace(self._settings_hooks)

        # CORNER MIKE — the companion that holds the corner while the workspace
        # is away. It is the "floating" surface the controller already knows how
        # to drive, so no new wiring is needed for status/reply to surface there.
        self.corner = CornerPresence()

        self.controller = UIController(
            runtime=self.runtime,
            page=self.page,
            floating=self.corner,
            edge=None,
        )

        self._settings_hooks["on_voice_toggle"] = self.controller.set_voice_enabled
        self._settings_hooks["on_wake_toggle"] = self._set_wake
        self._settings_hooks["on_voice_changed"] = self.controller.reload_voice
        # Conversations: History opens/deletes them, the rail starts new ones.
        self._settings_hooks["new_conversation"] = self.controller.new_conversation
        self._settings_hooks["open_conversation"] = self.controller.open_conversation
        self._settings_hooks["current_conversation"] = lambda: self.controller.conversation_id

        self.setCentralWidget(self.page)

        self._configure_window()
        self._configure_shortcuts()

        self.corner.expand_requested.connect(self._show_full)

        # Reachable from any application, not just when Mike has focus.
        self.hotkey = GlobalHotkey(self._summon)
        _optional("the global hotkey", self.hotkey.register)

        _optional("the IDE bridge", ide_manager.start)
        _optional("the VS Code extension", self._offer_vscode_extension)

        self._build_tray()
        self._torn_down = False
        self._quitting = False

        self.page.state_changed.connect(self._ambient_signal)
        self.page.dismiss_requested.connect(self._go_corner)
        self.page.minimise_requested.connect(self._go_corner)
        self.page.maximise_requested.connect(self._toggle_maximise)
        self.corner.dismissed.connect(self._on_corner_dismissed)

        self.controller.startup()
        self.page.set_wake_listening(self.controller.wake_listening)

    def _set_wake(self, enabled: bool) -> None:
        self.controller.set_wake_word_enabled(enabled)
        self.page.set_wake_listening(self.controller.wake_listening)

    # ── ambient tray notifications while Mike is away ──────
    _AMBIENT = {
        "needs_user": ("Mike needs you", "There's a decision waiting."),
        "error": ("Mike stopped", "Something needs a look."),
        "done": ("Mike finished", "The task is done."),
    }

    def _ambient_signal(self, state: str) -> None:
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
        self._tray_menu = QMenu(self)
        self._tray_menu.addAction("Open Mike", self._show_full)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction("Quit Mike", self._request_quit)

        self.tray = QSystemTrayIcon(_tray_icon(), self)
        self.tray.setToolTip("Mike")
        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_full()

    def _offer_vscode_extension(self) -> bool:
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
        self._show_full()
        self.page.input.focus()
        self._tour = None

    def _request_quit(self) -> None:
        self._quitting = True
        QApplication.instance().quit()

    # ── window geometry: opens large, remembers where it was ──────
    def _configure_window(self):
        self.setWindowTitle("Mike")
        # A real top-level window (Qt.Window), just without the OS title bar
        # (FramelessWindowHint). Qt.Window keeps it a first-class window rather
        # than a popup, which — together with _ensure_taskbar_button below —
        # is what puts Mike in the taskbar like any other app.
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("QMainWindow { background: transparent; }")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self._taskbar_fixed = False

        from config import preferences

        try:
            avail = QApplication.primaryScreen().availableGeometry()
        except Exception:
            avail = None

        w = int(preferences.get("window_w", -1) or -1)
        h = int(preferences.get("window_h", -1) or -1)
        x = int(preferences.get("window_x", -1) or -1)
        y = int(preferences.get("window_y", -1) or -1)

        if w < self.MIN_WIDTH or h < self.MIN_HEIGHT:
            w, h = self.DEFAULT_W, self.DEFAULT_H
        if avail is not None:
            # Never larger than the screen, never stranded off it.
            w = min(w, avail.width())
            h = min(h, avail.height())
            if x < avail.left() or x + w > avail.right() or y < avail.top() or y + h > avail.bottom():
                x = avail.center().x() - w // 2
                y = avail.center().y() - h // 2
        self.resize(w, h)
        if x >= 0 and y >= 0:
            self.move(x, y)

        if bool(preferences.get("window_maximised", False)):
            QTimer.singleShot(0, self._restore_maximised)

    def _restore_maximised(self) -> None:
        self.showMaximized()
        self.page.set_maximised(True)

    def _save_geometry(self) -> None:
        from config import preferences
        try:
            maxed = self.isMaximized()
            preferences.set_value("window_maximised", bool(maxed))
            geo = self.normalGeometry() if maxed else self.geometry()
            if geo.width() >= self.MIN_WIDTH and geo.height() >= self.MIN_HEIGHT:
                preferences.set_value("window_w", int(geo.width()))
                preferences.set_value("window_h", int(geo.height()))
                preferences.set_value("window_x", int(geo.x()))
                preferences.set_value("window_y", int(geo.y()))
        except Exception:
            logger.debug("Could not save window geometry.", exc_info=True)

    # ── FULL ↔ CORNER ─────────────────────────────────────
    def _show_full(self) -> None:
        """Bring the workspace forward and put the corner companion away."""
        self.corner.dismiss()
        self.showNormal() if self.isMinimized() else None
        self.show()
        self.raise_()
        self.activateWindow()
        self.page.input.focus()

    def _go_corner(self) -> None:
        """Send the workspace to the taskbar and leave Mike in the corner.

        Minimised, not hidden: a minimised window keeps its taskbar button, so
        Mike is still 'in the dock' and one click away, while the corner
        companion handles quick interaction. (Hiding it removed the taskbar
        entry entirely — the "no mike in the dock" report.)
        """
        self._save_geometry()
        self.showMinimized()
        try:
            self.corner.show_presence()
        except Exception:
            logger.exception("Could not show the corner presence.")

    def _on_corner_dismissed(self) -> None:
        """The corner was closed by its ✕. Mike is not lost — the window stays
        minimised in the taskbar, reachable by a click, the tray, or the
        hotkey."""
        if not self.isMinimized():
            self.showMinimized()

    def _ensure_taskbar_button(self) -> None:
        """Force a taskbar button for the frameless window.

        A frameless top-level on Windows is a WS_POPUP, which the shell may
        leave *out* of the taskbar. Setting WS_EX_APPWINDOW (and clearing
        WS_EX_TOOLWINDOW) tells the shell to give it a taskbar button like a
        normal application — the concrete fix for "no mike in the dock".
        """
        if getattr(self, "_taskbar_fixed", False):
            return
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex = (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            # Nudge the shell to pick up the changed extended style, so the
            # taskbar button appears without needing a hide/show flicker.
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            self._taskbar_fixed = True
        except Exception:
            logger.debug("Could not force a taskbar button.", exc_info=True)

    def _summon(self) -> None:
        """Global hotkey: toggle between the full workspace and the corner."""
        if self.isVisible() and not self.isMinimized():
            self._go_corner()
        else:
            self._show_full()

    # ── window controls: maximise / native move+resize ────
    def _toggle_maximise(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.page.set_maximised(False)
        else:
            self.showMaximized()
            self.page.set_maximised(True)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.page.set_maximised(self.isMaximized())

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_taskbar_button()
        self.corner.dismiss()

    _RESIZE_MARGIN = 6      # logical px; scaled to the display below

    def nativeEvent(self, event_type, message):
        # Native move and resize for a frameless window via WM_NCHITTEST, in
        # PHYSICAL pixels (the window's own GetWindowRect and a DPI-scaled
        # margin), so it behaves like an OS window on a scaled display.
        if event_type == "windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    gx = ctypes.c_short(msg.lParam & 0xFFFF).value
                    gy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

                    rect = wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(
                        int(self.winId()), ctypes.byref(rect))
                    x = gx - rect.left
                    y = gy - rect.top
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top

                    dpr = self.devicePixelRatioF() or 1.0
                    m = max(4, int(self._RESIZE_MARGIN * dpr))

                    on_left, on_right = x < m, x > w - m
                    on_top, on_bottom = y < m, y > h - m

                    if not self.isMaximized():
                        if on_top and on_left:      return True, 13  # HTTOPLEFT
                        if on_top and on_right:     return True, 14  # HTTOPRIGHT
                        if on_bottom and on_left:   return True, 16  # HTBOTTOMLEFT
                        if on_bottom and on_right:  return True, 17  # HTBOTTOMRIGHT
                        if on_left:                 return True, 10  # HTLEFT
                        if on_right:                return True, 11  # HTRIGHT
                        if on_top:                  return True, 12  # HTTOP
                        if on_bottom:               return True, 15  # HTBOTTOM

                    # The titlebar's empty span is a drag handle (double-click to
                    # maximise); its buttons — window controls, the sidebar
                    # toggle, new chat — stay clickable.
                    from PySide6.QtCore import QPoint
                    local = QPoint(int(x / dpr), int(y / dpr))
                    if self.page.hit_is_caption(local):
                        return True, 2                              # HTCAPTION
                    return True, 1                                  # HTCLIENT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _configure_shortcuts(self):
        # A new chat really is new: Mike forgets the old one (it stays in
        # History). Ctrl+L used to clear only the screen while Mike silently
        # kept the whole conversation in context.
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.controller.new_conversation)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.controller.new_conversation)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.page.toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.page.open_settings)
        QShortcut(
            QKeySequence.Quit if platform.system() == "Darwin" else QKeySequence("Ctrl+Q"),
            self, activated=self._request_quit,
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F6:
            self.controller.voice_shortcut_pressed()
            return
        if event.key() == Qt.Key_Escape:
            if self.page.showing_overlay():
                self.page.close_overlays()
            else:
                # Stops whatever Mike is doing — a running turn, or just the
                # voice still reading a finished answer aloud.
                self.controller.cancel_active()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Closing the window is not quitting Mike — it's sending him to the
        corner. Real shutdown only ever happens through _request_quit (the
        tray's Quit item, or Ctrl+Q), which sets _quitting first."""
        if getattr(self, "_quitting", False):
            self._save_geometry()
            event.accept()
            return
        event.ignore()
        self._go_corner()

    def _teardown(self) -> None:
        if getattr(self, "_torn_down", False):
            return
        self._torn_down = True

        self._save_geometry()
        self.controller.shutdown()

        try:
            from tools.terminal.actions import shutdown_all
            shutdown_all()
        except Exception:
            logger.exception("Could not stop background processes.")

        ide_manager.stop()
        self.hotkey.unregister()
        self.tray.hide()
        self.corner.close()


def _maybe_show_welcome(window) -> None:
    """The first-install tour, shown exactly once per machine."""
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

    # Garbage-collect only on the GUI thread. Mike's busy background threads
    # (wake word, Piper, speech-to-text, workers) would otherwise trigger
    # collections that finalise Qt objects on the wrong thread and crash.
    from ui.system.main_thread_gc import MainThreadGC
    app._main_thread_gc = MainThreadGC(app)

    from ui.panel import style
    # Mike's typeface (Source Serif 4, bundled) — registered before anything
    # is built, so every surface is drawn in it from the first frame.
    style.load_fonts()
    style.apply_theme()

    app.setWindowIcon(_app_icon())
    # The one place the base UI font is set: Mike's face at the body size,
    # which any widget without a size of its own inherits.
    app.setFont(style.font(style.BODY))
    app.setStyleSheet(GLOBAL_STYLESHEET)

    # Mike stays present after the window closes (hotkey, wake word, corner,
    # tray), so Qt must not quit when the last window closes.
    app.setQuitOnLastWindowClosed(False)

    window = MikeWindow()

    _maybe_show_welcome(window)

    app.aboutToQuit.connect(window._teardown)

    if getattr(window, "_tour", None) is None:
        window.show()

    code = app.exec()

    window._teardown()

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    run()
