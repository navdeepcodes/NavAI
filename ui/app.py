from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QKeyEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from brain.core_runtime import CoreRuntime

from ide import manager as ide_manager
from ui.controller.ui_controller import UIController
from ui.edge.edge_surface import EdgeSurface
from ui.system.global_hotkey import GlobalHotkey
from ui.home.home_page import HomePage
from ui.theme import colors
from ui.theme.stylesheet import GLOBAL_STYLESHEET
from ui.widgets.floating.floating_window import FloatingWindow


class MikeWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.runtime = CoreRuntime()

        # The settings surface edits real engines, so it is handed the
        # controller's own switches rather than its own copies of state.
        self._settings_hooks = {}
        self.page = HomePage(self._settings_hooks)

        self.floating = FloatingWindow()

        self.edge = EdgeSurface()

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
        self.hotkey.register()

        # Listen for an editor. Mike works exactly the same if none ever
        # connects, or if the port is already taken.
        ide_manager.start()

        self.controller.startup()

    def _configure_window(self):

        self.setWindowTitle("Mike")

        self.resize(1120, 760)

        self.setMinimumSize(860, 620)

        self.setStyleSheet(
            f"QMainWindow {{ background: {colors.HOME_GROUND}; }}"
        )

    def _configure_shortcuts(self):

        QShortcut(
            QKeySequence("Ctrl+L"),
            self,
            activated=self.page.clear,
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

    def _summon(self) -> None:
        """Global invocation: bring Mike forward wherever the user is."""

        self.edge.dismiss()

        if self.floating.isVisible():
            self.floating.dismiss()
            return

        self.floating.activate()
        self.floating.raise_()
        self.floating.activateWindow()

    def _expand_from_floating(self) -> None:
        self.floating.dismiss()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):

        self.controller.shutdown()
        ide_manager.stop()
        self.hotkey.unregister()
        self.edge.close()
        self.floating.close()

        super().closeEvent(event)


def run():

    app = QApplication(sys.argv)

    app.setApplicationName("Mike")

    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = MikeWindow()

    # closeEvent misses quit paths that don't close the window (Cmd-Q, an
    # explicit quit), which would leave worker threads running at teardown.
    app.aboutToQuit.connect(window.controller.shutdown)

    window.show()

    code = app.exec()

    window.controller.shutdown()

    # A worker parked in a blocking model request can't be interrupted, so Qt
    # would abort destroying its thread. We're exiting anyway — leave without
    # running C++ destructors rather than crashing on the way out.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":

    run()
