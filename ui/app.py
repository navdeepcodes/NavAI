from __future__ import annotations

import sys

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow

from brain.runtime import MikeRuntime

from ui.controller.ui_controller import UIController
from ui.pages.chat_page import ChatPage
from ui.theme.stylesheet import GLOBAL_STYLESHEET


class MikeWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.runtime = MikeRuntime()

        self.page = ChatPage()

        self.controller = UIController(
            runtime=self.runtime,
            page=self.page,
        )

        self.setCentralWidget(self.page)

        self._configure_window()

        self._configure_shortcuts()

        self.controller.startup()

    def _configure_window(self):

        self.setWindowTitle("Mike")

        self.resize(1280,800)

        self.setMinimumSize(1024,720)

    def _configure_shortcuts(self):

        QShortcut(
            QKeySequence("Ctrl+L"),
            self,
            activated=self.page.clear,
        )

    def closeEvent(self,event):

        self.controller.shutdown()

        super().closeEvent(event)


def run():

    app = QApplication(sys.argv)

    app.setApplicationName("Mike")

    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = MikeWindow()

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":

    run()