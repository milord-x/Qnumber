from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QEvent, QEasingCurve, QObject, QPropertyAnimation, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QGraphicsOpacityEffect,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.pages.dataset_page import DatasetPage
from ui.pages.home_page import HomePage
from ui.pages.placeholder_page import PlaceholderPage


@dataclass(frozen=True)
class Routes:
    HOME: str = "home"
    DATASET: str = "dataset"
    TRAIN: str = "train"
    TEST: str = "test"
    OPTIONS: str = "options"


# project root: .../Qnumber
ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
BG_PATH = (ASSETS_DIR / "gallery_bg.png").resolve().as_posix()


APP_QSS = """
/* -------------------------------------------------
   GLOBAL
------------------------------------------------- */
QMainWindow { background: #000000; }

QWidget#Root {
    background: #000000;
}

QWidget {
    color: #EDEDED;
    font-family: Inter, Segoe UI, Arial;
    font-size: 13px;
    background: transparent;
}

/* -------------------------------------------------
   BUTTONS
------------------------------------------------- */
QPushButton, QToolButton {
    background: #0B0B0B;
    border: 1px solid #1C1C1C;
    border-radius: 12px;
    padding: 10px 14px;
    text-align: left;
}
QPushButton:hover, QToolButton:hover {
    border: 1px solid #2A2A2A;
    background: #101010;
}
QPushButton:pressed, QToolButton:pressed {
    background: #141414;
}

/* short click indicator (not state) */
QToolButton[activePulse="true"] {
    border: 1px solid #ECECEC;
    background: rgba(236, 236, 236, 0.08);
}

/* Active indicator ONLY for topbar buttons where we explicitly enable it */
QToolButton[activeIndicator="true"]:checked {
    border: 1px solid #ECECEC;
    background: rgba(236, 236, 236, 0.08);
}

/* Make Desc/Asc look default even when checked */
QToolButton#BtnOrder:checked {
    border: 1px solid #1C1C1C;
    background: #0B0B0B;
}

/* Choose specific styling request */
QToolButton#BtnChoose {
    border: 1px solid #ECECEC;
    background: rgba(236, 236, 236, 0.06);
}
QToolButton#BtnChoose:hover {
    background: rgba(236, 236, 236, 0.09);
}
QToolButton#BtnChoose:checked {
    background: rgba(236, 236, 236, 0.12);
}

/* Generate/Draw */
QPushButton#BtnGenerate { border: 1px solid #2B2B2B; }
QPushButton#BtnDraw     { border: 1px solid #232323; }

QListView::item:selected {
    background: transparent;
    color: #EDEDED;
}

QListView {
    selection-background-color: transparent;
    selection-color: #EDEDED;
}

/* -------------------------------------------------
   MENUS
------------------------------------------------- */
QMenu {
    background: #0B0B0B;
    border: 1px solid #1C1C1C;
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 10px;
    border-radius: 10px;
    color: #EDEDED;
}
QMenu::item:selected { background: #141414; }
QMenu::separator {
    height: 1px;
    background: #1C1C1C;
    margin: 6px 4px;
}

/* -------------------------------------------------
   LABELS
------------------------------------------------- */
QLabel#Muted      { color: #BDBDBD; }
QLabel#ActionInfo { color: #BDBDBD; }

/* -------------------------------------------------
   PANELS
------------------------------------------------- */
QFrame#GalleryBlock, QFrame#ActionPanel, QFrame#DatasetStub {
    background: #000000;
    border: 1px solid #141414;
    border-radius: 16px;
}

QListView#GalleryView {
    background: #000000;
    border: none;
    outline: 0;
}

/* -------------------------------------------------
   SCROLLBAR (unchanged visuals)
------------------------------------------------- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 6px 2px 6px 2px;
}
QScrollBar::handle:vertical {
    background: #1F1F1F;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #2A2A2A; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class ClickFadeFilter(QObject):
    """
    Global click feedback: fades any QAbstractButton for a short time after click.
    Important: must be installed on QApplication to see events from all widgets.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease and isinstance(obj, QAbstractButton):
            self._fade(obj)
        return False

    def _fade(self, btn: QAbstractButton) -> None:
        if not btn.isEnabled():
            return
    
        eff = btn.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(btn)
            btn.setGraphicsEffect(eff)
    
        # Stop any running animation stored on the button itself
        old_anim = getattr(btn, "_fade_anim", None)
        if old_anim is not None:
            try:
                old_anim.stop()
            except Exception:
                pass
    
        eff.setOpacity(1.0)
    
        anim = QPropertyAnimation(eff, b"opacity")
        anim.setDuration(220)
        anim.setStartValue(1.0)
        anim.setEndValue(0.70)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    
        def _restore() -> None:
            try:
                eff.setOpacity(1.0)
            except Exception:
                pass
            btn._fade_anim = None
    
        anim.finished.connect(_restore)
    
        # Store animation on button (safe lifetime)
        setattr(btn, "_fade_anim", anim)
    
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

class BackgroundWidget(QWidget):
    def __init__(self, image_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap(image_path)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        if self._pixmap.isNull():
            return

        # scale like CSS "cover"
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Qnumber")
        self.setMinimumSize(1100, 700)

        self._routes = Routes()

        root = BackgroundWidget(BG_PATH)
        root.setObjectName("Root")
        root.setStyleSheet(APP_QSS)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.stack = QStackedWidget()

        self.pages: dict[str, QWidget] = {
            self._routes.HOME: HomePage(on_navigate=self.navigate),
            self._routes.DATASET: DatasetPage(on_home=lambda: self.navigate(self._routes.HOME)),
            self._routes.TRAIN: PlaceholderPage("Training", "Training controls and metrics will live here."),
            self._routes.TEST: PlaceholderPage("Test", "Inference and evaluation will live here."),
            self._routes.OPTIONS: PlaceholderPage("Options", "Configuration and resets will live here."),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.stack)
        self.setCentralWidget(root)

        # Global fade for ALL buttons across ALL pages
        #self._click_fade = ClickFadeFilter(self)
        #app = QApplication.instance()
        #if app is not None:
        #    app.installEventFilter(self._click_fade)

        self.navigate(self._routes.HOME)

    def navigate(self, route: str) -> None:
        page = self.pages.get(route)
        if page is not None:
            self.stack.setCurrentWidget(page)