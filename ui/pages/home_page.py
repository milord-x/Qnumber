from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QRect, QRectF, QSize, QTimer, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QFont, QPixmap, QMovie, QPainterPath, QRegion
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QGraphicsOpacityEffect,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT_DIR / "assets"


def font_px(px: int, weight: int) -> QFont:
    f = QFont()
    f.setFamilies(["Inter", "SF Pro Display", "Segoe UI", "Arial"])
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def find_background() -> Optional[Path]:
    for name in ("background.gif", "background.png"):
        p = ASSETS_DIR / name
        if p.exists():
            return p
    return None


def rounded_mask(w: int, h: int, r: int) -> QRegion:
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, float(w), float(h)), float(r), float(r))
    return QRegion(path.toFillPolygon().toPolygon())


@dataclass(frozen=True)
class CardSpec:
    title: str
    route: str
    icon_png: str


class BlurCard(QFrame):
    def __init__(self, spec: CardSpec, *, on_click: Callable[[str], None]) -> None:
        super().__init__()
        self.spec = spec
        self.on_click = on_click

        self.setObjectName("BlurCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._radius = 16
        self._inset = 1

        self.setStyleSheet("""
            QFrame#BlurCard {
                border: 1px solid rgba(255,255,255,22);
                border-radius: 16px;
                background: rgba(0,0,0,0);
            }
        """)

        self.bg = QLabel(self)
        self.bg.setScaledContents(True)
        self.bg.setStyleSheet("background: transparent;")

        self.tint = QFrame(self)
        self.tint.setStyleSheet("background: rgba(0,0,0,70);")

        self.content = QFrame(self)
        self.content.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(self.content)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.icon.setStyleSheet("background: transparent;")
        self.icon.setMinimumHeight(92)

        p = ASSETS_DIR / spec.icon_png
        self._icon_path: Optional[Path] = p if p.exists() else None
        if self._icon_path is not None:
            self.icon.setPixmap(QPixmap(str(self._icon_path)))

        self.title = QLabel(spec.title)
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.title.setStyleSheet("color: white; background: transparent;")
        self.title.setFont(font_px(16, QFont.Weight.Black))

        lay.addWidget(self.icon, 1)
        lay.addWidget(self.title, 0)

        op = QGraphicsOpacityEffect(self)
        op.setOpacity(0.985)
        self.setGraphicsEffect(op)

        self._window_bg: Optional[QPixmap] = None

    def _safe_click(self, route: str):
        if self.window() is None:
            return
        if not self.isVisible():
            return
        self.on_click(route)

    def set_window_background(self, pm: Optional[QPixmap]) -> None:
        self._window_bg = pm

    def refresh_blur(self) -> None:
        if self._window_bg is None or self._window_bg.isNull():
            self.bg.clear()
            return
    
        top_left = self.mapTo(self.window(), self.rect().topLeft())
        rect = QRect(top_left.x(), top_left.y(), self.width(), self.height())
    
        # CLAMP RECT INSIDE PIXMAP
        bg_rect = self._window_bg.rect()
        rect = rect.intersected(bg_rect)
    
        if rect.isEmpty():
            self.bg.clear()
            return
    
        crop = self._window_bg.copy(rect)
    
        w = max(1, crop.width() // 6)
        h = max(1, crop.height() // 6)
    
        small = crop.scaled(
            w,
            h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    
        blurred = small.scaled(
            crop.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    
        self.bg.setPixmap(blurred)

    def resizeEvent(self, event):
        r = self.rect()
        inner = r.adjusted(self._inset, self._inset, -self._inset, -self._inset)

        self.bg.setGeometry(inner)
        self.tint.setGeometry(inner)
        self.content.setGeometry(inner)

        rr = max(1, self._radius - self._inset)
        m = rounded_mask(inner.width(), inner.height(), rr)
        self.bg.setMask(m)
        self.tint.setMask(m)

        self.bg.lower()
        self.tint.raise_()
        self.content.raise_()

        if self._icon_path is not None:
            target = QSize(min(104, inner.width() - 28), min(104, inner.height() - 64))
            pm = QPixmap(str(self._icon_path))
            self.icon.setPixmap(pm.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
    
        # no geometry animation
        super().mousePressEvent(event)
    
    
    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
    
        if self.rect().contains(event.position().toPoint()):
            self.on_click(self.spec.route)
    
        super().mouseReleaseEvent(event)

class HomePage(QWidget):
    def __init__(self, *, on_navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.on_navigate = on_navigate
        self.setStyleSheet("background: black;")

        self._bg_label: Optional[QLabel] = None
        self._bg_movie: Optional[QMovie] = None
        self._bg_pix: Optional[QPixmap] = None

        self._bg_scaled_cache: Optional[QPixmap] = None
        self._bg_scaled_cache_size: QSize = QSize()

        self._setup_background_optional()

        self.fg = QFrame(self)
        self.fg.setStyleSheet("background: transparent;")
        fg_layout = QVBoxLayout(self.fg)
        fg_layout.setContentsMargins(28, 22, 60, 60)
        fg_layout.setSpacing(0)

        self._logo_path = ASSETS_DIR / "qnumber.png"
        self._logo_original: Optional[QPixmap] = None

        self.title = QLabel()
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.title.setStyleSheet("background: transparent;")

        if self._logo_path.exists():
            self._logo_original = QPixmap(str(self._logo_path))
            self.title.setPixmap(self._logo_original)
        else:
            self.title.setText("Qnumber")
            self.title.setStyleSheet("color: white; background: transparent;")
            self.title.setFont(font_px(140, QFont.Weight.Black))

        fg_layout.addWidget(self.title, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        fg_layout.addStretch(1)

        row_wrap = QFrame()
        row_wrap.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        specs = [
            CardSpec("Training", "train", "training.png"),
            CardSpec("Dataset", "dataset", "dataset.png"),
            CardSpec("Test", "test", "test.png"),
            CardSpec("Options", "options", "options.png"),
        ]

        self.cards: list[BlurCard] = []
        for s in specs:
            c = BlurCard(s, on_click=self._go)
            c.setFixedSize(170, 170)
            self.cards.append(c)
            row.addWidget(c)

        fg_layout.addWidget(row_wrap, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        self._blur_throttle = QTimer(self)
        self._blur_throttle.setSingleShot(True)
        self._blur_throttle.setInterval(33)  # ~30 fps max
        self._blur_throttle.timeout.connect(self._refresh_all_card_blurs)
        
        if self._bg_movie is not None:
            self._bg_movie.frameChanged.connect(lambda _: self._schedule_blur_refresh())
        
        self._schedule_blur_refresh()

    def _schedule_blur_refresh(self) -> None:
        if not self._blur_throttle.isActive():
            self._blur_throttle.start()

    def _setup_background_optional(self) -> None:
        bg = find_background()
        if bg is None:
            return

        self._bg_label = QLabel(self)
        self._bg_label.setGeometry(self.rect())
        self._bg_label.setScaledContents(True)
        self._bg_label.lower()

        if bg.suffix.lower() == ".gif":
            self._bg_movie = QMovie(str(bg))
            self._bg_movie.setCacheMode(QMovie.CacheMode.CacheNone)
            self._bg_label.setMovie(self._bg_movie)
            self._bg_movie.start()
        else:
            self._bg_pix = QPixmap(str(bg))
            self._bg_label.setPixmap(self._bg_pix)

    def _current_window_bg_pixmap(self) -> Optional[QPixmap]:
        if self._bg_movie is not None:
            fr = self._bg_movie.currentPixmap()
            if fr.isNull():
                return None
            return fr

        if self._bg_pix is not None and not self._bg_pix.isNull():
            return self._bg_pix.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        return None

    def _refresh_all_card_blurs(self) -> None:
        pm = self._current_window_bg_pixmap()
        for c in self.cards:
            c.set_window_background(pm)
            c.refresh_blur()

    def _go(self, route: str) -> None:
        self.on_navigate(route)

    def resizeEvent(self, event):
        if self._bg_label is not None:
            self._bg_label.setGeometry(self.rect())
            if self._bg_movie is not None:
                self._bg_movie.setScaledSize(self.size())
                self._schedule_blur_refresh()

        self.fg.setGeometry(self.rect())

        self._bg_scaled_cache = None
        self._bg_scaled_cache_size = QSize()

        if self._logo_original is not None and not self._logo_original.isNull():
            target_w = max(300, int(self.width() * 0.4))
            scaled = self._logo_original.scaledToWidth(
                target_w,
                Qt.TransformationMode.SmoothTransformation
            )
            self.title.setPixmap(scaled)

        super().resizeEvent(event)