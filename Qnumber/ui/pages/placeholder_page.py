from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("Card")
        c = QVBoxLayout(card)
        c.setContentsMargins(18, 18, 18, 18)
        c.setSpacing(8)

        t = QLabel(title)
        t.setObjectName("Title")

        s = QLabel(subtitle)
        s.setObjectName("SubTitle")
        s.setWordWrap(True)

        hint = QLabel("This screen is a stub. Home navigation is already wired.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        c.addWidget(t)
        c.addWidget(s)
        c.addSpacing(6)
        c.addWidget(hint)
        c.addStretch(1)

        layout.addWidget(card)
        layout.addStretch(1)