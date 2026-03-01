from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
)

from ui.pages.home_page import HomePage
from ui.pages.placeholder_page import PlaceholderPage


@dataclass(frozen=True)
class Routes:
    HOME: str = "home"
    DATASET: str = "dataset"
    TRAIN: str = "train"
    TEST: str = "test"
    OPTIONS: str = "options"


APP_QSS = """
/* Global */
QMainWindow {
    background: black;
}
QWidget {
    color: #EDEDED;
    font-family: Inter, Segoe UI, Arial;
    font-size: 13px;
}

/* Buttons */
QPushButton {
    background: #0B0B0B;
    border: 1px solid #1C1C1C;
    border-radius: 10px;
    padding: 10px 14px;
    text-align: left;
}
QPushButton:hover {
    border: 1px solid #2A2A2A;
    background: #0F0F0F;
}
QPushButton:pressed {
    background: #141414;
}

/* Labels */
QLabel#Title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#SubTitle {
    font-size: 12px;
    color: #BDBDBD;
}
QLabel#CardTitle {
    font-size: 14px;
    font-weight: 600;
}
QLabel#Muted {
    color: #BDBDBD;
}

/* Cards */
QFrame#Card {
    background: #050505;
    border: 1px solid #141414;
    border-radius: 14px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Qnumber")
        self.setMinimumSize(1100, 700)
        self.setContentsMargins(0, 0, 0, 0)

        self._routes = Routes()

        root = QWidget()
        root.setStyleSheet(APP_QSS)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.stack = QStackedWidget()

        self.pages: dict[str, QWidget] = {
            self._routes.HOME: HomePage(on_navigate=self.navigate),
            self._routes.DATASET: PlaceholderPage("Dataset", "Dataset tools will live here."),
            self._routes.TRAIN: PlaceholderPage("Training", "Training controls and metrics will live here."),
            self._routes.TEST: PlaceholderPage("Test", "Inference and evaluation will live here."),
            self._routes.OPTIONS: PlaceholderPage("Options", "Configuration and resets will live here."),
        }

        for _, page in self.pages.items():
            self.stack.addWidget(page)

        layout.addWidget(self.stack)
        self.setCentralWidget(root)

        self.navigate(self._routes.HOME)

    def navigate(self, route: str) -> None:
        page = self.pages.get(route)
        if page is None:
            return
        self.stack.setCurrentWidget(page)