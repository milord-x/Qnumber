from __future__ import annotations

from typing import Callable
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton


class GeneratePage(QWidget):
    def __init__(self, *, on_back: Callable[[], None]) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("Это страница Generate")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_back = QPushButton("Back")
        btn_back.clicked.connect(on_back)

        root.addStretch(1)
        root.addWidget(title)
        root.addWidget(btn_back, 0, Qt.AlignmentFlag.AlignCenter)
        root.addStretch(1)