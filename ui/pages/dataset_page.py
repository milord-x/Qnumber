from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
from PyQt6.QtGui import QPixmap

import os
import re
import uuid

from PyQt6.QtCore import (
    Qt,
    QSize,
    QAbstractListModel,
    QModelIndex,
    QObject,
    QRunnable,
    QThreadPool,
    pyqtSignal,
    QTimer,
    QFileSystemWatcher,
    QVariantAnimation,
    QPoint,
    QEvent,
)
from PyQt6.QtGui import (
    QAction,
    QPixmap,
    QPainter,
    QPen,
    QBrush,
    QColor,
    QFont,
    QImageReader,
    QWheelEvent,
    QMouseEvent,
)
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QPushButton,
    QToolButton,
    QListView,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QSizePolicy,
    QMenu,
    QDialog,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT_DIR / "dataset"

# --------------------------------
#        Tunable constants
# --------------------------------
ACTION_PANEL_WIDTH = 659
MAX_COLUMNS = 6
TILE_W = 180
TILE_H = 180
TILE_SPACING = 12
SCROLL_SPEED_FACTOR = 0.35
AUTO_SCROLL_MARGIN = 42
AUTO_SCROLL_BASE_STEP = 10
AUTO_SCROLL_MAX_STEP = 80
AUTO_SCROLL_INTERVAL_MS = 16

# ---------- MenuButton ----------
class MenuButton(QToolButton):
    changed = pyqtSignal(str)

    def __init__(self, items: list[str], *, initial: str) -> None:
        super().__init__()
        self._items = items
        self._value = initial
        self.setText(initial)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu(self)
        menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        for it in items:
            act = QAction(it, self)
            act.triggered.connect(lambda _, v=it: self._set_value(v))
            menu.addAction(act)

        self.setMenu(menu)

    def value(self) -> str:
        return self._value

    def _set_value(self, v: str) -> None:
        if v == self._value:
            return
        self._value = v
        self.setText(v)
        self.changed.emit(v)

@dataclass(frozen=True)

class GalleryItem:
    path: Path
    digit: int
    split: str
    index: int
    mtime: float

class _PixmapReadyEmitter(QObject):
    pixmap_ready = pyqtSignal(str)

class _LoadPixmapTask(QRunnable):
    def __init__(
        self,
        *,
        path: Path,
        target: QSize,
        cache: dict[str, QPixmap],
        emitter: _PixmapReadyEmitter,
    ) -> None:
        super().__init__()
        self.path = path
        self.target = target
        self.cache = cache
        self.emitter = emitter

    def run(self) -> None:
        try:
            reader = QImageReader(str(self.path))
            reader.setAutoTransform(True)
            img = reader.read()
            if img.isNull():
                return
            pm = QPixmap.fromImage(img).scaled(
                self.target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.cache[str(self.path)] = pm
            self.emitter.pixmap_ready.emit(str(self.path))
        except Exception:
            return


def _parse_index(filename: str) -> Optional[int]:
    stem = filename.rsplit(".", 1)[0]
    if "_" not in stem:
        return None
    tail = stem.rsplit("_", 1)[-1]
    if not tail.isdigit():
        return None
    try:
        return int(tail)
    except Exception:
        return None

class _ReindexDoneEmitter(QObject):
    finished = pyqtSignal(bool, str)


class _ReindexDatasetTask(QRunnable):
    def __init__(self, *, dataset_dir: Path, emitter: _ReindexDoneEmitter) -> None:
        super().__init__()
        self.dataset_dir = dataset_dir
        self.emitter = emitter

    @staticmethod
    def _is_valid_name(name: str) -> bool:
        return bool(re.match(r"^[0-9]_[0-9]{5}\.png$", name, re.IGNORECASE))

    def run(self) -> None:
        try:
            # Global reindex per split (train/test), but keep files inside digit folders.
            # Result:
            #   dataset/<split>/<digit>/<digit>_<global_index:05d>.png
            # where global_index is unique within the split.
    
            rx = re.compile(r"^([0-9])_([0-9]{5})\.png$", re.IGNORECASE)
    
            for split in ("train", "test"):
                split_dir = self.dataset_dir / split
                if not split_dir.exists():
                    continue
    
                items: list[tuple[int, str]] = []  # (digit, filename)
                # Collect all valid files across digit folders
                for d in range(10):
                    digit_dir = split_dir / str(d)
                    if not digit_dir.exists():
                        continue
    
                    with os.scandir(digit_dir) as it:
                        for e in it:
                            if not e.is_file():
                                continue
                            if not e.name.lower().endswith(".png"):
                                continue
                            if not rx.match(e.name):
                                continue
                            items.append((d, e.name))
    
                if not items:
                    continue
    
                # stable deterministic order: digit first, then name
                items.sort(key=lambda t: (t[0], t[1]))
    
                tag = uuid.uuid4().hex[:10]
    
                # Phase A: rename everything to temporary unique names (avoid collisions)
                temp: list[tuple[int, str]] = []  # (digit, tmp_name)
                for i, (d, name) in enumerate(items):
                    digit_dir = split_dir / str(d)
                    old_p = digit_dir / name
                    tmp_name = f"__tmp__{tag}__{i:06d}.png"
                    old_p.rename(digit_dir / tmp_name)
                    temp.append((d, tmp_name))
    
                # Phase B: global numbering within split
                for global_i, (d, tmp_name) in enumerate(temp):
                    digit_dir = split_dir / str(d)
                    final_name = f"{d}_{global_i:05d}.png"
                    (digit_dir / tmp_name).rename(digit_dir / final_name)
    
            self.emitter.finished.emit(True, "Reindex complete (global per split)")
        except Exception as e:
            self.emitter.finished.emit(False, f"Reindex failed: {e}")

class GalleryModel(QAbstractListModel):
    ROLE_ITEM = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, *, dataset_dir: Path) -> None:
        super().__init__()
        self.dataset_dir = dataset_dir

        self._all: list[GalleryItem] = []
        self._visible: list[GalleryItem] = []

        self._split_filter: str = "All"
        self._digit_filter: str = "All"
        self._sort_key: str = "Index"
        self._sort_desc: bool = True

        self._icon_size = QSize(96, 96)

        self._cache: dict[str, QPixmap] = {}
        self._emitter = _PixmapReadyEmitter()
        self._emitter.pixmap_ready.connect(self._on_pixmap_ready)
        self._pool = QThreadPool.globalInstance()

        self._cache["__placeholder__"] = self._make_placeholder(self._icon_size)

    def set_icon_size(self, s: QSize) -> None:
        if s == self._icon_size:
            return
        self._icon_size = s
        self._cache = {"__placeholder__": self._make_placeholder(self._icon_size)}
        if self.rowCount() > 0:
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0))

    def reload_from_disk(self) -> None:
        items: list[GalleryItem] = []

        for split in ("train", "test"):
            split_dir = self.dataset_dir / split
            if not split_dir.exists():
                continue

            for d in range(10):
                digit_dir = split_dir / str(d)
                if not digit_dir.exists():
                    continue

                for p in digit_dir.glob("*.png"):
                    idx = _parse_index(p.name)
                    if idx is None:
                        continue
                    try:
                        mt = p.stat().st_mtime
                    except Exception:
                        mt = 0.0
                    items.append(GalleryItem(path=p, digit=d, split=split, index=idx, mtime=mt))

        self.beginResetModel()
        self._all = items
        self._visible = list(items)
        self._apply_filters_and_sort_locked()
        self.endResetModel()

    def set_filters(self, *, split: str, digit: str) -> None:
        self._split_filter = split
        self._digit_filter = digit
        self._refilter()

    def set_sort(self, *, key: str, desc: bool) -> None:
        self._sort_key = key
        self._sort_desc = desc
        self._resort()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._visible)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._visible):
            return None

        item = self._visible[row]
        spath = str(item.path)

        if role == int(Qt.ItemDataRole.DecorationRole):
            pm = self._cache.get(spath)
            if pm is not None:
                return pm

            if spath not in self._cache:
                self._cache[spath] = self._cache["__placeholder__"]
                self._pool.start(_LoadPixmapTask(
                    path=item.path, target=self._icon_size, cache=self._cache, emitter=self._emitter
                ))
            return self._cache["__placeholder__"]

        if role == int(Qt.ItemDataRole.DisplayRole):
            split_short = "T" if item.split == "train" else "E"
            return f"{split_short} {item.digit} {item.index:05d}"

        if role == self.ROLE_ITEM:
            return item

        return None

    def _on_pixmap_ready(self, path_str: str) -> None:
        for i, it in enumerate(self._visible):
            if str(it.path) == path_str:
                ix = self.index(i, 0)
                self.dataChanged.emit(ix, ix, [int(Qt.ItemDataRole.DecorationRole)])
                break

    def _refilter(self) -> None:
        self.beginResetModel()
        self._visible = list(self._all)
        self._apply_filters_and_sort_locked()
        self.endResetModel()

    def _resort(self) -> None:
        self.beginResetModel()
        self._apply_sort_locked()
        self.endResetModel()

    def _apply_filters_and_sort_locked(self) -> None:
        self._apply_filter_locked()
        self._apply_sort_locked()

    def _apply_filter_locked(self) -> None:
        if self._split_filter in ("Train", "Test"):
            wanted = self._split_filter.lower()
            self._visible = [x for x in self._visible if x.split == wanted]

        if self._digit_filter != "All Digits":
            try:
                d = int(self._digit_filter)
                self._visible = [x for x in self._visible if x.digit == d]
            except Exception:
                pass

    def _apply_sort_locked(self) -> None:
        key = self._sort_key
        desc = self._sort_desc

        if key == "Newest":
            self._visible.sort(key=lambda x: x.mtime, reverse=desc)
        elif key == "Oldest":
            self._visible.sort(key=lambda x: x.mtime, reverse=not desc)
        elif key == "Digit":
            self._visible.sort(key=lambda x: (x.digit, x.index), reverse=desc)
        elif key == "Index":
            self._visible.sort(key=lambda x: x.index, reverse=desc)

    @staticmethod
    def _make_placeholder(size: QSize) -> QPixmap:
        w, h = max(1, size.width()), max(1, size.height())
        pm = QPixmap(w, h)
        pm.fill(QColor(8, 8, 8))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(28, 28, 28), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 12, 12)
        painter.end()
        return pm


class GalleryDelegate(QStyledItemDelegate):
    def __init__(self, *, show_labels: bool = True) -> None:
        super().__init__()
        self.show_labels = show_labels
        self._font = QFont()
        self._font.setFamilies(["Inter", "Segoe UI", "Arial"])
        self._font.setPixelSize(12)
        self._font.setWeight(QFont.Weight.Bold)

    def set_show_labels(self, v: bool) -> None:
        self.show_labels = v

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(6, 6, -6, -6)
        radius = 14

        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        bg = QColor(6, 6, 6, 210)
        border = QColor(24, 24, 24, 230)
        if hovered:
            bg = QColor(10, 10, 10, 220)
            border = QColor(38, 38, 38, 240)
        if selected:
            bg = QColor(236, 236, 236, 22)
            border = QColor(236, 236, 236, 255) 

        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, radius, radius)

        pm: QPixmap = index.data(int(Qt.ItemDataRole.DecorationRole))
        label: str = index.data(int(Qt.ItemDataRole.DisplayRole)) or ""

        pad = 10
        label_h = 18 if self.show_labels else 0
        img_rect = rect.adjusted(pad, pad, -pad, -(pad + label_h))

        if isinstance(pm, QPixmap) and not pm.isNull():
            x = img_rect.x() + (img_rect.width() - pm.width()) // 2
            y = img_rect.y() + (img_rect.height() - pm.height()) // 2
            painter.drawPixmap(x, y, pm)

        if self.show_labels:
            painter.setFont(self._font)
            painter.setPen(QColor(220, 220, 220))
            text_rect = rect.adjusted(pad, rect.height() - (pad + label_h), -pad, -pad)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

        painter.restore()

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(TILE_W, TILE_H)


# --------- Pixel Grid Viewer ----------
class PixelGridWidget(QWidget):
    def __init__(self, img_path: Path) -> None:
        super().__init__()
        self.img_path = img_path
        self.setMinimumSize(520, 520)

        reader = QImageReader(str(img_path))
        reader.setAutoTransform(True)
        self.img = reader.read()
        self.scale = 16

    def paintEvent(self, event) -> None:
        if self.img.isNull():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        iw = self.img.width()
        ih = self.img.height()

        draw_w = iw * self.scale
        draw_h = ih * self.scale

        x0 = (self.width() - draw_w) // 2
        y0 = (self.height() - draw_h) // 2

        for y in range(ih):
            for x in range(iw):
                c = QColor(self.img.pixel(x, y))
                p.fillRect(x0 + x * self.scale, y0 + y * self.scale, self.scale, self.scale, c)

        grid_pen = QPen(QColor(60, 60, 60, 180), 1)
        p.setPen(grid_pen)
        for x in range(iw + 1):
            px = x0 + x * self.scale
            p.drawLine(px, y0, px, y0 + draw_h)
        for y in range(ih + 1):
            py = y0 + y * self.scale
            p.drawLine(x0, py, x0 + draw_w, py)

        p.setPen(QPen(QColor(120, 120, 120, 220), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x0, y0, draw_w, draw_h)
        p.end()


class ImageViewerDialog(QDialog):
    def __init__(self, img_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(img_path.name)
        self.setModal(True)
        self.resize(720, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top = QHBoxLayout()
        lbl = QLabel(str(img_path))
        lbl.setObjectName("Muted")
        lbl.setWordWrap(True)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        top.addWidget(lbl, 1)
        top.addWidget(btn_close, 0)
        root.addLayout(top)

        viewer = PixelGridWidget(img_path)
        root.addWidget(viewer, 1)


# --------- Slower-scrolling list view ----------
class SlowScrollListView(QListView):
    """
    Scroll slowed down + file-manager-like marquee selection.

    Rule:
      - Double click arms marquee anywhere (empty or on an item)
      - If user drags after double click -> marquee selection (multi)
      - If user does NOT drag -> request open ONLY if double click was on an item
    """

    open_requested = pyqtSignal(QModelIndex)

    def _auto_scroll_tick(self) -> None:
        if not self._marquee_active or self._last_mouse_pos is None:
            self._auto_scroll_timer.stop()
            self._auto_v = 0.0
            return
    
        vp = self.viewport()
        y = self._last_mouse_pos.y()
        h = vp.height()
        if h <= 0:
            return
    
        target = 0.0
    
        # near top
        if y < AUTO_SCROLL_MARGIN:
            t = (AUTO_SCROLL_MARGIN - y) / max(1, AUTO_SCROLL_MARGIN)  # 0..1
            speed = AUTO_SCROLL_BASE_STEP + (t * t) * (AUTO_SCROLL_MAX_STEP - AUTO_SCROLL_BASE_STEP)
            target = -speed
    
        # near bottom
        elif y > h - AUTO_SCROLL_MARGIN:
            t = (y - (h - AUTO_SCROLL_MARGIN)) / max(1, AUTO_SCROLL_MARGIN)  # 0..1
            speed = AUTO_SCROLL_BASE_STEP + (t * t) * (AUTO_SCROLL_MAX_STEP - AUTO_SCROLL_BASE_STEP)
            target = speed
    
        # Smooth approach to target (low-pass)
        alpha = 0.22  # smaller = smoother, larger = snappier
        self._auto_v = (1.0 - alpha) * self._auto_v + alpha * target
    
        # Deadzone to stop micro-jitter
        if abs(self._auto_v) < 0.5:
            self._auto_v = 0.0
    
        if self._auto_v != 0.0:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() + int(self._auto_v))

    def _auto_scroll_update_pos(self, pos: QPoint) -> None:
        self._last_mouse_pos = pos
        if self._marquee_active:
            if not self._auto_scroll_timer.isActive():
                self._auto_scroll_timer.start()
        else:
            self._auto_scroll_timer.stop()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._marquee_armed = False
        self._press_pos: Optional[QPoint] = None
        self._marquee_active = False

        # If double-click was on an item, we keep it pending until we know it's not a drag.
        self._pending_open: Optional[QModelIndex] = None

        # Default: normal single selection
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setSelectionRectVisible(False)

        # Avoid drag/drop behavior interfering with marquee
        self.setDragEnabled(False)
        self.setDragDropMode(QListView.DragDropMode.NoDragDrop)

        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(AUTO_SCROLL_INTERVAL_MS)
        self._auto_scroll_timer.timeout.connect(self._auto_scroll_tick)

        self._last_mouse_pos: Optional[QPoint] = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return

        # Arm marquee after double click (anywhere)
        self._marquee_armed = True

        # Remember item under cursor (if any), but do not let default doubleClicked fire
        ix = self.indexAt(event.position().toPoint())
        self._pending_open = ix if ix.isValid() else None

        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._marquee_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._marquee_armed
            and (event.buttons() & Qt.MouseButton.LeftButton)
            and self._press_pos is not None
            and not self._marquee_active
        ):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= 6:
                self._marquee_active = True

                # Drag means: do NOT open viewer
                self._pending_open = None

                # Enable multi-select + rubber band rectangle
                self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
                self.setSelectionRectVisible(True)

                # Re-send a press so Qt starts rubber-band reliably
                fake = QMouseEvent(
                    QEvent.Type.MouseButtonPress,
                    event.position(),
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    event.modifiers(),
                )
                super().mousePressEvent(fake)

        self._auto_scroll_update_pos(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # If user double-clicked an item and did NOT drag -> open it now
        if (not self._marquee_active) and self._pending_open is not None:
            self.open_requested.emit(self._pending_open)

        # Reset state after one action
        self._pending_open = None
        if self._marquee_active or self._marquee_armed:
            self._marquee_armed = False
            self._marquee_active = False
            self._press_pos = None
            self.setSelectionRectVisible(False)
            self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._auto_scroll_timer.stop()
        self._last_mouse_pos = None
        self._auto_v = 0.0
    def wheelEvent(self, event: QWheelEvent) -> None:
        sb = self.verticalScrollBar()

        pd = event.pixelDelta().y()
        ad = event.angleDelta().y()

        if pd != 0:
            delta = pd
        elif ad != 0:
            delta = int(ad / 2)
        else:
            super().wheelEvent(event)
            return

        scaled = int(delta * SCROLL_SPEED_FACTOR)
        if scaled == 0:
            scaled = 1 if delta > 0 else -1

        sb.setValue(sb.value() - scaled)
        event.accept()
        self._auto_v = 0.0

class ConfirmDialog(QDialog):
    def __init__(self, *, title: str, message: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setFixedSize(420, 180)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        root.addWidget(lbl, 1)

        row = QHBoxLayout()
        row.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_ok = QPushButton("Confirm")

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)

        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)

        root.addLayout(row)

class SplitPickDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Delete all")
        self.setFixedSize(420, 170)

        self.choice: Optional[str] = None  # "train" or "test"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        lbl = QLabel("Choose which split to delete:")
        lbl.setWordWrap(True)
        root.addWidget(lbl, 1)

        row = QHBoxLayout()
        row.addStretch(1)

        btn_cancel = QPushButton("Cancel")
        btn_train = QPushButton("Train")
        btn_test = QPushButton("Test")

        btn_cancel.clicked.connect(self.reject)
        btn_train.clicked.connect(lambda: self._pick("train"))
        btn_test.clicked.connect(lambda: self._pick("test"))

        row.addWidget(btn_cancel)
        row.addWidget(btn_train)
        row.addWidget(btn_test)

        root.addLayout(row)

    def _pick(self, v: str) -> None:
        self.choice = v
        self.accept()

# ----------------- DatasetPage -----------------
class DatasetPage(QWidget):
    def __init__(self, *, on_home: Callable[[], None]) -> None:
        super().__init__()
        self.on_home = on_home

        self.stack = QStackedWidget(self)

        self.gallery_screen = GalleryScreen(on_home=self.on_home)
        self.generate_stub = _StubScreen("Generate", on_back=self.show_gallery)
        self.draw_stub = _StubScreen("Draw", on_back=self.show_gallery)

        self.stack.addWidget(self.gallery_screen)
        self.stack.addWidget(self.generate_stub)
        self.stack.addWidget(self.draw_stub)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.stack)

        self.gallery_screen.action_panel.btn_generate.clicked.connect(self.show_generate)
        self.gallery_screen.action_panel.btn_draw.clicked.connect(self.show_draw)

        # selection sync
        self.gallery_screen.gallery_block.view.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_selection_ui()
        )

        # delete from topbar
        self.gallery_screen.gallery_block.topbar.btn_delete.clicked.connect(self._delete_selected)
        self.gallery_screen.gallery_block.topbar.btn_reindex.clicked.connect(self._start_reindex)
        self.gallery_screen.gallery_block.delete_all_requested.connect(self._delete_all_split)

        # realtime filesystem sync
        self._watcher = QFileSystemWatcher(self)
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.timeout.connect(self._reload_model)

        self._reindex_emitter = _ReindexDoneEmitter()
        self._reindex_emitter.finished.connect(self._on_reindex_finished)
        self._reindex_pool = QThreadPool.globalInstance()
        self._reindex_running = False

        self.gallery_screen.gallery_block.topbar.btn_split.changed.connect(
            lambda *_: QTimer.singleShot(0, self._sync_selection_ui)
        )
        self.gallery_screen.gallery_block.topbar.btn_digit.changed.connect(
            lambda *_: QTimer.singleShot(0, self._sync_selection_ui)
        )

        self._install_watchers()

        self._reload_model()
        self.show_gallery()

    def show_gallery(self) -> None:
        self.stack.setCurrentWidget(self.gallery_screen)

    def show_generate(self) -> None:
        self.stack.setCurrentWidget(self.generate_stub)

    def show_draw(self) -> None:
        self.stack.setCurrentWidget(self.draw_stub)

    # ---------------- realtime sync ----------------
    def _install_watchers(self) -> None:
        for p in self._watcher.directories():
            self._watcher.removePath(p)
        for p in self._watcher.files():
            self._watcher.removePath(p)

        watch_dirs: list[Path] = []
        for split in ("train", "test"):
            split_dir = DATASET_DIR / split
            watch_dirs.append(split_dir)
            for d in range(10):
                watch_dirs.append(split_dir / str(d))

        for d in watch_dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        for d in watch_dirs:
            if d.exists():
                self._watcher.addPath(str(d))

        self._watcher.directoryChanged.connect(lambda _: self._schedule_reload())
        self._watcher.fileChanged.connect(lambda _: self._schedule_reload())

    def _schedule_reload(self) -> None:
        self._reload_timer.start(150)

    def _reload_model(self) -> None:
        self.gallery_screen.model.reload_from_disk()
        self._sync_selection_ui()

    def _start_reindex(self) -> None:
        if self._reindex_running:
            return
    
        dlg = ConfirmDialog(
            title="Reindex Dataset",
            message="This will rename ALL dataset files inside train/ and test/.\n\nAre you sure you want to continue?",
            parent=self,
        )
    
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
    
        self._reindex_running = True

        # stop filesystem spam during massive rename
        self._watcher.blockSignals(True)

        tb = self.gallery_screen.gallery_block.topbar
        tb.btn_reindex.setEnabled(False)
        tb.btn_delete.setEnabled(False)

        # simple status signal in UI
        self.gallery_screen.gallery_block.lbl_selected.setText("Reindexing...")

        self._reindex_pool.start(_ReindexDatasetTask(
            dataset_dir=DATASET_DIR,
            emitter=self._reindex_emitter,
        ))

    def _on_reindex_finished(self, ok: bool, msg: str) -> None:
        self._reindex_running = False

        # re-enable watcher + refresh model once
        self._watcher.blockSignals(False)
        self._reload_model()

        tb = self.gallery_screen.gallery_block.topbar
        tb.btn_reindex.setEnabled(True)

        # delete depends on selection; sync handles it
        self._sync_selection_ui()

        # show status
        self.gallery_screen.gallery_block.lbl_selected.setText(msg if ok else msg)

    # ---------------- selection + delete ----------------
    def _selected_items(self) -> list[GalleryItem]:
        sel = self.gallery_screen.gallery_block.view.selectionModel().selectedIndexes()
        items: list[GalleryItem] = []
        for ix in sel:
            it = ix.data(GalleryModel.ROLE_ITEM)
            if isinstance(it, GalleryItem):
                items.append(it)
        return items

    def _sync_selection_ui(self) -> None:
        items = self._selected_items()
        n = len(items)

        gb = self.gallery_screen.gallery_block
        
        # Files count respects current filters (All = train + test together)
        files_count = gb.model.rowCount()
        gb.lbl_files.setText(f"Files: {files_count}")
        
        # Selected count
        gb.lbl_selected.setText(f"Selected: {n}")

        # delete enabled if any selection exists
        self.gallery_screen.gallery_block.topbar.btn_delete.setEnabled(n >= 1)

    def _delete_selected(self) -> None:
        items = self._selected_items()
        if not items:
            return
    
        dlg = ConfirmDialog(
            title="Delete Confirmation",
            message=f"You are about to permanently delete {len(items)} file(s).\n\nThis action cannot be undone.",
            parent=self,
        )
    
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
    
        for it in items:
            try:
                it.path.unlink(missing_ok=True)
            except TypeError:
                try:
                    if it.path.exists():
                        it.path.unlink()
                except Exception:
                    pass
            except Exception:
                pass
    
        self.gallery_screen.gallery_block.view.clearSelection()
        self._schedule_reload()

    def _delete_all_split(self) -> None:
        pick = SplitPickDialog(parent=self)
        if pick.exec() != QDialog.DialogCode.Accepted:
            return
        if pick.choice not in ("train", "test"):
            return
    
        split = pick.choice
        split_title = "Train" if split == "train" else "Test"
    
        confirm = ConfirmDialog(
            title="Delete All Confirmation",
            message=f"You are about to permanently delete ALL files in {split_title}.\n\nThis action cannot be undone.",
            parent=self,
        )
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return
    
        # Avoid filesystem watcher spam during mass delete
        self._watcher.blockSignals(True)
        try:
            split_dir = DATASET_DIR / split
            for d in range(10):
                digit_dir = split_dir / str(d)
                if not digit_dir.exists():
                    continue
                for p in digit_dir.glob("*.png"):
                    try:
                        p.unlink(missing_ok=True)
                    except TypeError:
                        try:
                            if p.exists():
                                p.unlink()
                        except Exception:
                            pass
                    except Exception:
                        pass
        finally:
            self._watcher.blockSignals(False)
    
        self.gallery_screen.gallery_block.view.clearSelection()
        self._reload_model()

class _StubScreen(QFrame):
    def __init__(self, title: str, *, on_back: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("DatasetStub")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.clicked.connect(on_back)
        top.addWidget(btn_back, 0, Qt.AlignmentFlag.AlignLeft)
        top.addStretch(1)
        lay.addLayout(top)

        t = QLabel(f"{title} screen is not implemented yet.")
        lay.addWidget(t)
        lay.addStretch(1)


class GalleryScreen(QWidget):
    def __init__(self, *, on_home: Callable[[], None]) -> None:
        super().__init__()

        self.gallery_block = GalleryBlock(on_home=on_home)
        self.action_panel = ActionPanel()

        self.action_panel.setFixedWidth(ACTION_PANEL_WIDTH)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(self.gallery_block, 1)
        row.addWidget(self.action_panel, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)  # keep untouched
        root.setSpacing(0)
        root.addLayout(row)

        self.model = self.gallery_block.model


class GalleryBlock(QFrame):
    delete_all_requested = pyqtSignal()
    def __init__(self, *, on_home: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("GalleryBlock")

        self.topbar = GalleryTopBar(on_home=on_home)

        self.view = SlowScrollListView()
        self.view.setObjectName("GalleryView")

        self.model = GalleryModel(dataset_dir=DATASET_DIR)
        self.delegate = GalleryDelegate(show_labels=True)

        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)

        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSpacing(TILE_SPACING)
        self.view.setIconSize(QSize(96, 96))
        self.view.setMouseTracking(True)

        self.view.open_requested.connect(self._open_viewer)

        # bottom-left info (files + selected)
        self.lbl_files = QLabel("Files: 0")
        self.lbl_files.setObjectName("Muted")
        
        self.lbl_selected = QLabel("Selected: 0")
        self.lbl_selected.setObjectName("Muted")
        
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)
        bottom.addWidget(self.lbl_files, 0, Qt.AlignmentFlag.AlignLeft)
        bottom.addWidget(self.lbl_selected, 0, Qt.AlignmentFlag.AlignLeft)
        bottom.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addWidget(self.topbar)
        lay.addWidget(self.view, 1)
        bottom_wrap = QHBoxLayout()
        bottom_wrap.setContentsMargins(0, 0, 0, 0)
        bottom_wrap.setSpacing(0)
        bottom_wrap.addLayout(bottom)
        
        lay.addLayout(bottom_wrap, 0)

        self.topbar.btn_options.clicked.connect(self._open_options_menu)

        self.topbar.btn_split.changed.connect(self._on_filters_changed)
        self.topbar.btn_digit.changed.connect(self._on_filters_changed)
        self.topbar.btn_sort.changed.connect(self._on_sort_changed)
        self.topbar.btn_order.toggled.connect(self._on_sort_changed)

        self._apply_grid_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_grid_layout()

    def _apply_grid_layout(self) -> None:
        vw = self.view.viewport().width()
        if vw <= 0:
            return
        cols = max(1, min(MAX_COLUMNS, vw // (TILE_W + TILE_SPACING)))
        total_spacing = (cols + 1) * TILE_SPACING
        available = max(1, vw - total_spacing)
        tile_w = max(140, min(TILE_W, available // cols))
        tile_h = TILE_H
        self.view.setGridSize(QSize(tile_w + TILE_SPACING, tile_h + TILE_SPACING))

    def _on_filters_changed(self) -> None:
        self.model.set_filters(
            split=self.topbar.btn_split.value(),
            digit=self.topbar.btn_digit.value(),
        )

    def _on_sort_changed(self) -> None:
        desc = self.topbar.btn_order.isChecked()
        self.topbar.btn_order.setText("Desc" if desc else "Asc")
        self.model.set_sort(key=self.topbar.btn_sort.value(), desc=desc)

    def _open_options_menu(self) -> None:
        menu = QMenu(self)
        menu.setObjectName("OptionsMenu")
        menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        act_small = menu.addAction("Preview: Small")
        act_medium = menu.addAction("Preview: Medium")
        act_large = menu.addAction("Preview: Large")
        menu.addSeparator()
        act_labels = menu.addAction("Show labels")
        act_labels.setCheckable(True)
        act_labels.setChecked(self.delegate.show_labels)

        def set_size(px: int) -> None:
            self.view.setIconSize(QSize(px, px))
            self.model.set_icon_size(QSize(px, px))
            self.view.viewport().update()

        def toggle_labels(checked: bool) -> None:
            self.delegate.set_show_labels(checked)
            self.view.viewport().update()

        act_small.triggered.connect(lambda: set_size(72))
        act_medium.triggered.connect(lambda: set_size(96))
        act_large.triggered.connect(lambda: set_size(128))
        act_labels.toggled.connect(toggle_labels)
        act_delete_all = menu.addAction("Delete all…")
        act_delete_all.triggered.connect(self.delete_all_requested.emit)
        menu.addSeparator()

        menu.exec(self.topbar.btn_options.mapToGlobal(self.topbar.btn_options.rect().bottomLeft()))

    def _open_viewer(self, index: QModelIndex) -> None:
        it = index.data(GalleryModel.ROLE_ITEM)
        if not isinstance(it, GalleryItem):
            return
        dlg = ImageViewerDialog(it.path, parent=self)
        dlg.exec()


class GalleryTopBar(QFrame):
    def __init__(self, *, on_home: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("GalleryTopBar")

        self.btn_home = QToolButton()
        self.btn_home.setText("Home")
        self.btn_home.clicked.connect(on_home)

        self.btn_options = QToolButton()
        self.btn_options.setText("Options")

        # Reindex / Sort dataset filenames (safe renumber)
        self.btn_reindex = QToolButton()
        self.btn_reindex.setText("Reindex")

        # (5) Delete button near options; enabled only if selection > 0
        self.btn_delete = QToolButton()
        self.btn_delete.setText("Delete")
        self.btn_delete.setEnabled(False)

        self.btn_split = MenuButton(
            ["All Data", "Train", "Test"],
            initial="All Data"
        )
        
        self.btn_digit = MenuButton(
            ["All Digits"] + [str(i) for i in range(10)],
            initial="All Digits"
        )

        self.btn_sort = MenuButton(["Newest", "Oldest", "Digit", "Index"], initial="Index")

        self.btn_order = QToolButton()
        self.btn_order.setCheckable(True)
        self.btn_order.setChecked(True)
        self.btn_order.setText("Desc")

        left = QHBoxLayout()
        left.setSpacing(10)
        left.addWidget(self.btn_home)
        left.addWidget(self.btn_options)
        left.addWidget(self.btn_delete)
        left.addWidget(self.btn_reindex)
        left.addWidget(self.btn_split)
        left.addWidget(self.btn_digit)
        left.addStretch(1)

        right = QHBoxLayout()
        right.setSpacing(10)
        # (7) removed "Sort:" label
        right.addWidget(self.btn_sort)
        right.addWidget(self.btn_order)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addLayout(left, 1)
        row.addLayout(right, 0)


class _ActionCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, *, title: str, desc: str, button_object_name: str, icon_path: str) -> None:
        super().__init__()
        self.setObjectName("ActionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._hover_t = 0.0  # 0..1
        self._press_t = 0.0  # 0..1

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(160)
        self._hover_anim.valueChanged.connect(self._on_hover_anim)

        self._press_anim = QVariantAnimation(self)
        self._press_anim.setDuration(90)
        self._press_anim.valueChanged.connect(self._on_press_anim)

        self.icon = QLabel()
        self.icon.setObjectName("ActionCardIcon")
        ICON_SIZE = 92

        self.icon.setFixedSize(ICON_SIZE, ICON_SIZE)

        pm = QPixmap(icon_path)
        if not pm.isNull():
           pm = pm.scaled(
            ICON_SIZE, ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
           )
           self.icon.setPixmap(pm)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("ActionCardTitle")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(1)
        title_row.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.lbl_title, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)

        self.lbl_desc = QLabel(desc)
        self.lbl_desc.setObjectName("ActionCardDesc")
        self.lbl_desc.setWordWrap(True)

        # Arrow/Open button (keeps objectName used by your code: BtnDraw / BtnGenerate)
        self.btn_open = QToolButton()
        self.btn_open.setObjectName(button_object_name)
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setText("›")
        self.btn_open.setAutoRaise(True)
        self.btn_open.clicked.connect(self.clicked)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(8)
        text_col.addLayout(title_row)
        text_col.addWidget(self.lbl_desc, 1)

        row = QHBoxLayout(self)
        row.setContentsMargins(18, 16, 18, 16)
        row.setSpacing(14)
        row.addLayout(text_col, 1)
        row.addWidget(self.btn_open, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._apply_card_style()

    def _on_hover_anim(self, v) -> None:
        try:
            self._hover_t = float(v)
        except Exception:
            self._hover_t = 0.0
        self._apply_card_style()

    def _on_press_anim(self, v) -> None:
        try:
            self._press_t = float(v)
        except Exception:
            self._press_t = 0.0
        self._apply_card_style()

    def enterEvent(self, e) -> None:
        self._start_anim(self._hover_anim, self._hover_t, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._start_anim(self._hover_anim, self._hover_t, 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, self._press_t, 1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._press_t > 0.0:
            self._start_anim(self._press_anim, self._press_t, 0.0)
        if e.button() == Qt.MouseButton.LeftButton:
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(e)

    @staticmethod
    def _start_anim(anim: QVariantAnimation, start: float, end: float) -> None:
        anim.stop()
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.start()

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def _apply_card_style(self) -> None:
        t = max(0.0, min(1.0, self._hover_t))
        p = max(0.0, min(1.0, self._press_t))

        bg_base = 10.0
        bg_hover = 18.0
        bg = self._lerp(bg_base, bg_hover, t) - (2.0 * p)

        br_a = self._lerp(0.18, 0.34, t)

        title = int(self._lerp(230, 245, t))
        desc = int(self._lerp(150, 175, t))

        btn_bg_a = self._lerp(0.10, 0.18, t)
        btn_border_a = self._lerp(0.18, 0.30, t)

        self.setStyleSheet(
            f"""
            QFrame#ActionCard {{
                background-color: rgba({int(bg)},{int(bg)},{int(bg)},255);
                border: 1px solid rgba(255,255,255,{br_a});
                border-radius: 18px;
            }}
            QLabel#ActionCardTitle {{
                color: rgb({title},{title},{title});
                font-size: 28px;
                font-weight: 600;
            }}
            QLabel#ActionCardDesc {{
                color: rgb({desc},{desc},{desc});
                font-size: 15px;
            }}
            QToolButton#{self.btn_open.objectName()} {{
                color: rgb(235,235,235);
                background-color: rgba(255,255,255,{btn_bg_a});
                border: 1px solid rgba(255,255,255,{btn_border_a});
                border-radius: 12px;
                min-width: 46px;
                min-height: 46px;
                font-size: 26px;
                font-weight: 600;
            }}
            QToolButton#{self.btn_open.objectName()}:pressed {{
                background-color: rgba(255,255,255,0.08);
            }}
            """
        )


class ActionPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ActionPanel")

        draw_icon = str(ROOT_DIR / "assets" / "draw.png")
        gen_icon  = str(ROOT_DIR / "assets" / "generate.png")

        self.card_draw = _ActionCard(
            title="Draw",
            desc="Manually create labeled digit samples for the dataset. Use it to add precise ground-truth examples and edge cases.",
            button_object_name="BtnDraw",
            icon_path=draw_icon,
        )
        self.card_generate = _ActionCard(
            title="Generate",
            desc="Automatically create synthetic digit samples with variation. Use it to quickly expand and balance your dataset.",
            button_object_name="BtnGenerate",
            icon_path=gen_icon,
        )

        # IMPORTANT: keep same attribute names used elsewhere in your code
        self.btn_draw = self.card_draw.btn_open
        self.btn_generate = self.card_generate.btn_open

        # Clicking the whole card triggers the same open action
        self.card_draw.clicked.connect(self.btn_draw.click)
        self.card_generate.clicked.connect(self.btn_generate.click)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(16)
        lay.addWidget(self.card_draw)
        lay.addWidget(self.card_generate)
        lay.addStretch(1)

        self.setStyleSheet(
            """
            QFrame#ActionPanel {
                background: transparent;
                border: none;
            }
            """
        )