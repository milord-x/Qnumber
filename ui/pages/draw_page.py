from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import (
    Qt,
    QSize,
    QPoint,
    QRect,
    QPointF,
    QEvent,
    pyqtSignal,
    QTimer,
    QRectF,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QPixmap,
    QIcon,
    QImageReader,
    QLinearGradient,
    QRegularExpressionValidator,
    QImage,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QSizePolicy,
    QToolButton,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QStackedLayout,
    QGridLayout,
    QSlider,
)
from PyQt6.QtCore import QRegularExpression

BORDER_RGBA = "rgba(255,255,255,40)"
PILL_BG = "rgba(20,20,20,180)"
PILL_BORDER = "rgba(255,255,255,55)"

GRID_MINOR_A = 18
GRID_MAJOR_A = 34

CANVAS_SIZE = 620
CANVAS_CELLS = 32
CENTER_CARD_W = 660

ROOT_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT_DIR / "dataset"

ASSETS_DIR = ROOT_DIR / "assets"

PIXEL_BRUSH_ICON = ASSETS_DIR / "pixel_brush.png"
SMOOTH_BRUSH_ICON = ASSETS_DIR / "smooth_brush.png"
CIRCLE_BRUSH_ICON = ASSETS_DIR / "circle_brush.png"
SQUARE_BRUSH_ICON = ASSETS_DIR / "square_brush.png"
ERASER_ICON = ASSETS_DIR / "eraser.png"
COLOR_PICKER_ICON = ASSETS_DIR / "color_picker.png"

LEFT_PANEL_W = 410
TOP_TOOLS_W = 300
SAVE_PANEL_W = 360
CREATE_TILE_ICON = 92
CREATE_TILE_W = 118
CREATE_TILE_H = 118
CREATE_TILE_SPACING = 10


class DrawPage(QWidget):
    def __init__(self, *, on_back: Callable[[], None]) -> None:
        super().__init__()

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        
        self._on_back = on_back
        self._current_edit_path: Optional[Path] = None
        self._last_create_key: Optional[tuple[str, Optional[int]]] = None
        self.left_panel = _DrawLeftPanel(on_back=self._handle_back)
        self.left_panel.setFixedWidth(LEFT_PANEL_W)
        self.left_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        self.center = DrawCenterCard()
        self.center.setFixedWidth(CENTER_CARD_W)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        top_tools_row = QHBoxLayout()
        top_tools_row.setContentsMargins(0, 0, 0, 0)
        top_tools_row.setSpacing(12)

        self.tools_card = _ToolOptionsCard()
        self.tools_card.setFixedWidth(92)

        color_stack = QVBoxLayout()
        color_stack.setContentsMargins(0, 0, 0, 0)
        color_stack.setSpacing(12)

        self.color_card = _ColorToolsCard()
        self.color_card.setFixedWidth(TOP_TOOLS_W)

        self.size_bg_card = _BrushSettingsCard()
        self.size_bg_card.setFixedWidth(TOP_TOOLS_W)

        self.center.canvas.color_used.connect(self.color_card.commit_current_color_to_history)
        self.color_card.color_changed.connect(self.center.canvas.set_brush_color)

        self.tools_card.brush_mode_changed.connect(self.size_bg_card.set_brush_icon_mode)

        self.size_bg_card.background_mode_changed.connect(self.center.canvas.set_background_mode)
        self.size_bg_card.background_done_clicked.connect(self.center.canvas.set_background_hex)
        self.tools_card.active_tool_changed.connect(self.center.canvas.set_active_tool)
        self.tools_card.brush_shape_changed.connect(self.center.canvas.set_brush_shape)
        self.tools_card.brush_mode_changed.connect(self.center.canvas.set_brush_mode)
        self.center.canvas.color_picked.connect(self.color_card.set_external_color)

        self.size_bg_card.brush_size_changed.connect(self.center.canvas.set_brush_size)
        self.size_bg_card.eraser_size_changed.connect(self.center.canvas.set_eraser_size)

        color_stack.addWidget(self.color_card, 0, Qt.AlignmentFlag.AlignTop)
        color_stack.addWidget(self.size_bg_card, 0, Qt.AlignmentFlag.AlignTop)
        color_stack.addStretch(1)

        top_tools_row.addWidget(self.tools_card, 0, Qt.AlignmentFlag.AlignTop)
        top_tools_row.addLayout(color_stack, 0)

        right_col.addLayout(top_tools_row, 0)

        self.save_card = _SavePanelCard()
        self.save_card.setFixedWidth(SAVE_PANEL_W)

        right_col.addStretch(1)
        right_col.addWidget(self.save_card, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        center_host = QVBoxLayout()
        center_host.setContentsMargins(0, 0, 0, 0)
        center_host.setSpacing(0)
        center_host.addStretch(1)
        center_host.addWidget(self.center, 0, Qt.AlignmentFlag.AlignCenter)
        center_host.addStretch(1)
        
        body.addLayout(center_host, 1)
        body.addLayout(right_col, 0)

        root.addWidget(self.left_panel, 0)
        root.addLayout(body, 1)

        self.left_panel.filename_changed.connect(self.center.set_filename)
        self.left_panel.filename_changed.connect(self.save_card.set_filename_hint)
        
        self.left_panel.edit_image_selected.connect(self._handle_edit_image_selected)
        self.left_panel.clear_canvas_requested.connect(self.center.canvas.clear_image)
        
        self.left_panel.create_state_changed.connect(self._handle_create_state_changed)
        self.left_panel.mode_changed.connect(self._handle_mode_changed)

        self.save_card.save_requested.connect(self._handle_save_requested)

    def _handle_save_requested(self, count: int) -> None:
        mode = self.left_panel.mode()

        if mode == "create":
            state = self.left_panel.current_create_state()
            split = state["split"]
            digit = state["digit"]

            if split == "train" and digit is None:
                self.save_card.set_status("Select digit")
                return

            if not self.center.canvas.has_image_data():
                self.save_card.set_status("No data to save")
                return

            image = self.center.canvas.export_image()
            if image is None or image.isNull():
                self.save_card.set_status("No data to save")
                return

            start_idx = self.left_panel.next_create_index()
            saved = 0

            for offset in range(count):
                idx = start_idx + offset

                if split == "train":
                    save_dir = DATASET_DIR / "train" / str(digit)
                    save_dir.mkdir(parents=True, exist_ok=True)
                    save_path = save_dir / f"{digit}_{idx:05d}.png"
                else:
                    save_dir = DATASET_DIR / "test"
                    save_dir.mkdir(parents=True, exist_ok=True)
                    save_path = save_dir / f"{idx:05d}.png"

                if image.save(str(save_path), "PNG"):
                    saved += 1

            if saved <= 0:
                self.save_card.set_status("Save failed")
                return

            self.left_panel.refresh_create_panel()
            self.save_card.set_status(f"Saved {saved} image(s)")
            return

        if mode == "edit":
            if self._current_edit_path is None:
                self.save_card.set_status("Select image")
                return

            if not self.center.canvas.has_image_data():
                self.save_card.set_status("No data to save")
                return

            image = self.center.canvas.export_image()
            if image is None or image.isNull():
                self.save_card.set_status("No data to save")
                return

            ok = image.save(str(self._current_edit_path), "PNG")
            if not ok:
                self.save_card.set_status("Save failed")
                return

            self.save_card.set_status("Image updated")
            return

        self.save_card.set_status("Select mode")

    def _handle_back(self) -> None:
        self.reset_page()
        self._on_back()

    def _handle_edit_image_selected(self, path: str) -> None:
        self._current_edit_path = Path(path)
        self.center.canvas.load_image(path)
        self.save_card.set_filename_hint(self._current_edit_path.stem)

    def _handle_create_state_changed(self, state: dict) -> None:
        self.save_card.set_create_state(state)

        if self.left_panel.mode() != "create":
            return

        key = (state.get("split", "train"), state.get("digit"))
        if self._last_create_key is None:
            self._last_create_key = key
            return

        if key != self._last_create_key:
            self.center.canvas.clear_image()

        self._last_create_key = key

    def _handle_mode_changed(self, mode: Optional[str]) -> None:
        self.save_card.set_mode(mode)

        if mode != "edit":
            self._current_edit_path = None

        if mode is None:
            self._last_create_key = None
            self.save_card.set_filename_hint("Select mode")

    def reset_page(self) -> None:
        self.left_panel.reset_panel()
        self.center.reset_panel()
        self.tools_card.reset_panel()
        self.size_bg_card.reset_panel()
        self.color_card.reset_panel()
        self.save_card.reset_panel()
        
class _DrawLeftPanel(QWidget):
    filename_changed = pyqtSignal(str)
    edit_image_selected = pyqtSignal(str)
    clear_canvas_requested = pyqtSignal()
    create_state_changed = pyqtSignal(dict)
    mode_changed = pyqtSignal(object)

    def __init__(self, *, on_back: Callable[[], None]) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.mode_card = _DrawModeCard(on_back=on_back)
        self.create_card = _CreatePanelCard()
        self.edit_card = _EditPanelCard()

        self.mode_card.setFixedWidth(TOP_TOOLS_W)

        bottom_card_w = 410
        self.create_card.setFixedWidth(bottom_card_w)
        self.edit_card.setFixedWidth(bottom_card_w)
        self.create_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.mode_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.edit_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self.edit_card.image_selected.connect(self.edit_image_selected)
        self.edit_card.filename_changed.connect(self.filename_changed)

        self.bottom_host = QWidget()
        self.bottom_stack = QStackedLayout(self.bottom_host)
        self.bottom_stack.setContentsMargins(0, 0, 0, 0)
        
        self.bottom_empty = QWidget()
        
        self.bottom_stack.addWidget(self.bottom_empty)
        self.bottom_stack.addWidget(self.create_card)
        self.bottom_stack.addWidget(self.edit_card)
        self.bottom_stack.setCurrentWidget(self.bottom_empty)

        root.addWidget(
            self.mode_card,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        root.addWidget(
            self.bottom_host,
            1,
            Qt.AlignmentFlag.AlignLeft,
        )

        self.mode_card.create_clicked.connect(self._activate_create)
        self.mode_card.edit_clicked.connect(self._activate_edit)

        self.create_card.filename_changed.connect(self.filename_changed)
        self.create_card.state_changed.connect(self.create_state_changed)

    def _close_bottom_panel(self) -> None:
        self.mode_card.set_mode(None)
        self.bottom_stack.setCurrentWidget(self.bottom_empty)
        self.filename_changed.emit("Select mode")
        self.clear_canvas_requested.emit()
        self.create_card._sync_timer.stop()
        self.edit_card._sync_timer.stop()
        self.mode_changed.emit(None)
        self.create_state_changed.emit(self.create_card.current_state())

    def _activate_create(self) -> None:
        if self.mode_card.mode() == "create":
            self._close_bottom_panel()
            return

        self.mode_card.set_mode("create")
        self.bottom_stack.setCurrentWidget(self.create_card)
        self.create_card.refresh_all()
        self.create_card._sync_timer.start()
        self.edit_card._sync_timer.stop()
        self.mode_changed.emit("create")
        self.create_state_changed.emit(self.create_card.current_state())

    def _activate_edit(self) -> None:
        if self.mode_card.mode() == "edit":
            self._close_bottom_panel()
            return
    
        self.mode_card.set_mode("edit")
        self.bottom_stack.setCurrentWidget(self.edit_card)
        self.edit_card.refresh_all()
        self.edit_card._sync_timer.start()
        self.create_card._sync_timer.stop()
        self.mode_changed.emit("edit")
        self.create_state_changed.emit(self.create_card.current_state())

    def mode(self) -> Optional[str]:
        return self.mode_card.mode()

    def current_create_state(self) -> dict:
        return self.create_card.current_state()

    def next_create_index(self) -> int:
        return self.create_card.next_index()

    def refresh_create_panel(self) -> None:
        self.create_card.refresh_all()
        self.create_state_changed.emit(self.create_card.current_state())

    def reset_panel(self) -> None:
        self.create_card._sync_timer.stop()
        self.edit_card._sync_timer.stop()

        self.mode_card.set_mode(None)
        self.bottom_stack.setCurrentWidget(self.bottom_empty)

        self.create_card.reset_panel()
        self.edit_card.reset_panel()

        self.filename_changed.emit("Select mode")
        self.clear_canvas_requested.emit()
        self.mode_changed.emit(None)
        self.create_state_changed.emit(self.create_card.current_state())
class _DrawModeCard(QFrame):
    create_clicked = pyqtSignal()
    edit_clicked = pyqtSignal()

    def __init__(self, *, on_back: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("DrawModeCard")
        self._mode: Optional[str] = None

        self.setStyleSheet(f"""
            QFrame#DrawModeCard {{
                background: #000000;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QPushButton#DrawModeButton {{
                min-height: 36px;
                border-radius: 18px;
                font-size: 18px;
                font-weight: 600;
                padding: 10px 18px;
                text-align: center;
                color: rgba(255,255,255,150);
            }}
            QPushButton#DrawModeButton[active="true"] {{
                color: rgba(255,255,255,255);
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        self.btn_back = QToolButton()
        self.btn_back.setText("Back")
        self.btn_back.clicked.connect(on_back)

        top.addWidget(self.btn_back, 0, Qt.AlignmentFlag.AlignLeft)
        top.addStretch(1)

        self.btn_create = QPushButton("Create")
        self.btn_create.setObjectName("DrawModeButton")
        self.btn_create.setProperty("active", False)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setObjectName("DrawModeButton")
        self.btn_edit.setProperty("active", False)

        self.btn_create.clicked.connect(self.create_clicked.emit)
        self.btn_edit.clicked.connect(self.edit_clicked.emit)

        root.addLayout(top)
        root.addWidget(self.btn_create)
        root.addWidget(self.btn_edit)

    def set_mode(self, mode: Optional[str]) -> None:
        self._mode = mode

        self.btn_create.setProperty("active", mode == "create")
        self.btn_edit.setProperty("active", mode == "edit")

        self.btn_create.style().unpolish(self.btn_create)
        self.btn_create.style().polish(self.btn_create)

        self.btn_edit.style().unpolish(self.btn_edit)
        self.btn_edit.style().polish(self.btn_edit)
    
    def mode(self) -> Optional[str]:
        return self._mode 

class _CreatePanelCard(QFrame):
    filename_changed = pyqtSignal(str)
    state_changed = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CreatePanelCard")
        self._split = "train"
        self._digit: Optional[int] = None
        
        self.setStyleSheet(f"""
            QFrame#CreatePanelCard {{
                background: #050505;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QPushButton#SplitButton {{
                min-height: 34px;
                border-radius: 16px;
                font-weight: 600;
                color: rgba(255,255,255,150);
            }}
            QPushButton#SplitButton[active="true"] {{
                color: rgba(255,255,255,255);
            }}
            QPushButton#DigitButton {{
                min-height: 30px;
                min-width: 30px;
                border-radius: 12px;
                font-weight: 600;
                color: rgba(255,255,255,150);
                padding: 6px 8px;
                text-align: center;
            }}
            QPushButton#DigitButton[active="true"] {{
                color: rgba(255,255,255,255);
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        split_row = QHBoxLayout()
        split_row.setContentsMargins(0, 0, 0, 0)
        split_row.setSpacing(10)

        self.btn_train = QPushButton("Train")
        self.btn_train.setObjectName("SplitButton")
        self.btn_train.setProperty("active", True)

        self.btn_test = QPushButton("Test")
        self.btn_test.setObjectName("SplitButton")
        self.btn_test.setProperty("active", False)

        self.btn_train.clicked.connect(lambda: self._set_split("train"))
        self.btn_test.clicked.connect(lambda: self._set_split("test"))

        split_row.addWidget(self.btn_train)
        split_row.addWidget(self.btn_test)

        self.digit_wrap = QWidget()
        digit_row = QGridLayout(self.digit_wrap)
        digit_row.setContentsMargins(0, 0, 0, 0)
        digit_row.setSpacing(6)

        self.digit_buttons: list[QPushButton] = []
        for d in range(10):
            b = QPushButton(str(d))
            b.setObjectName("DigitButton")
            b.setProperty("active", False)
            b.clicked.connect(lambda _, v=d: self._set_digit(v))
            self.digit_buttons.append(b)
        
            row = d // 5
            col = d % 5
        
            digit_row.addWidget(b, row, col)

        self.gallery = QListWidget()
        _setup_gallery_widget(self.gallery)
        self.gallery.itemDoubleClicked.connect(self._open_item)

        self.lbl_files = QLabel("Files: 0")
        self.lbl_files.setObjectName("Muted")

        root.addLayout(split_row)
        root.addWidget(self.digit_wrap)
        root.addWidget(self.gallery, 1)
        root.addWidget(self.lbl_files, 0, Qt.AlignmentFlag.AlignLeft)
        
        self._snapshot = _split_snapshot(self._split)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(800)
        self._sync_timer.timeout.connect(self._sync_from_disk)
        self._sync_timer.stop()

        self.refresh_all()

    def refresh_all(self) -> None:
        self._refresh_split_buttons()
        self._refresh_digit_visibility()
        self._refresh_digit_buttons()
        self._reload_gallery()
        self._emit_filename()
        self._snapshot = _split_snapshot(self._split)
        self.state_changed.emit(self.current_state())

    def _set_split(self, split: str) -> None:
        if split == self._split:
            return
        self._split = split
        if split == "test":
            self._digit = None
        self.refresh_all()
        self.state_changed.emit(self.current_state())

    def _set_digit(self, digit: int) -> None:
        self._digit = digit
        self._refresh_digit_buttons()
        self._emit_filename()
        self.state_changed.emit(self.current_state())

    def _refresh_split_buttons(self) -> None:
        self.btn_train.setProperty("active", self._split == "train")
        self.btn_test.setProperty("active", self._split == "test")
        self.btn_train.style().unpolish(self.btn_train)
        self.btn_train.style().polish(self.btn_train)
        self.btn_test.style().unpolish(self.btn_test)
        self.btn_test.style().polish(self.btn_test)

    def _refresh_digit_visibility(self) -> None:
        self.digit_wrap.setVisible(self._split == "train")

    def _refresh_digit_buttons(self) -> None:
        for i, b in enumerate(self.digit_buttons):
            b.setProperty("active", self._digit == i)
            b.style().unpolish(b)
            b.style().polish(b)

    def _reload_gallery(self) -> None:
        self.gallery.clear()

        paths = _collect_split_paths(self._split)

        for p in paths:
            self.gallery.addItem(_make_gallery_item(p))

        self.lbl_files.setText(f"Files: {len(paths)}")

    def _emit_filename(self) -> None:
        next_idx = self._next_global_index(self._split)

        if self._split == "train":
            if self._digit is None:
                self.filename_changed.emit("Select digit")
                return
            self.filename_changed.emit(f"{self._digit}_{next_idx:05d}")
            return

        self.filename_changed.emit(f"{next_idx:05d}")

    def _next_global_index(self, split: str) -> int:
        max_idx = -1
    
        for p in _collect_split_paths(split):
            v = _extract_index_from_name(p.stem)
            if v is not None and v > max_idx:
                max_idx = v
    
        return max_idx + 1

    def _sync_from_disk(self) -> None:
        cur = _split_snapshot(self._split)
        if cur == self._snapshot:
            return
        self._snapshot = cur
        self._reload_gallery()
        self._emit_filename()
        self.state_changed.emit(self.current_state())

    def _open_item(self, item: QListWidgetItem) -> None:
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        dlg = _PreviewDialog(Path(path_str), parent=self)
        dlg.exec()
    def current_state(self) -> dict:
        return {
            "split": self._split,
            "digit": self._digit,
            "next_index": self._next_global_index(self._split),
        }

    def next_index(self) -> int:
        return self._next_global_index(self._split)

    def reset_panel(self) -> None:
        self._sync_timer.stop()
        self._split = "train"
        self._digit = None
        self.refresh_all()

class _EditPanelCard(QFrame):
    image_selected = pyqtSignal(str)
    filename_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("EditPanelCard")
        self._split = "train"

        self.setStyleSheet(f"""
            QFrame#EditPanelCard {{
                background: #050505;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QPushButton#SplitButton {{
                min-height: 34px;
                border-radius: 16px;
                font-weight: 600;
                color: rgba(255,255,255,150);
            }}
                        QLineEdit#GallerySearch {{
                min-height: 34px;
                border-radius: 14px;
                padding: 0 12px;
                background: #090909;
                border: 1px solid rgba(255,255,255,40);
                color: #FFFFFF;
            }}
            QLineEdit#GallerySearch:focus {{
                border: 1px solid rgba(255,255,255,90);
            }}
            QPushButton#SplitButton[active="true"] {{
                color: rgba(255,255,255,255);
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        split_row = QHBoxLayout()
        split_row.setContentsMargins(0, 0, 0, 0)
        split_row.setSpacing(10)

        self.btn_train = QPushButton("Train")
        self.btn_train.setObjectName("SplitButton")
        self.btn_train.setProperty("active", True)

        self.btn_test = QPushButton("Test")
        self.btn_test.setObjectName("SplitButton")
        self.btn_test.setProperty("active", False)

        self.btn_train.clicked.connect(lambda: self._set_split("train"))
        self.btn_test.clicked.connect(lambda: self._set_split("test"))

        split_row.addWidget(self.btn_train)
        split_row.addWidget(self.btn_test)
        
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("GallerySearch")
        self.search_edit.setPlaceholderText("Search")
        self.search_edit.textChanged.connect(self._reload_gallery)
        
        self.gallery = QListWidget()
        _setup_gallery_widget(self.gallery)
        self.gallery.itemClicked.connect(self._select_item)
        self.gallery.itemDoubleClicked.connect(self._open_item_preview)

        self.lbl_files = QLabel("Files: 0")
        self.lbl_files.setObjectName("Muted")

        root.addLayout(split_row)
        root.addWidget(self.search_edit)
        root.addWidget(self.gallery, 1)
        root.addWidget(self.lbl_files, 0, Qt.AlignmentFlag.AlignLeft)
        self._snapshot = _split_snapshot(self._split)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(800)
        self._sync_timer.timeout.connect(self._sync_from_disk)
        self._sync_timer.start()

    def refresh_all(self) -> None:
        self._refresh_split_buttons()
        self._reload_gallery()
        self.filename_changed.emit("Select image")
        self._snapshot = _split_snapshot(self._split)

    def _set_split(self, split: str) -> None:
        if split == self._split:
            return
        self._split = split
        self.refresh_all()

    def _refresh_split_buttons(self) -> None:
        self.btn_train.setProperty("active", self._split == "train")
        self.btn_test.setProperty("active", self._split == "test")
        self.btn_train.style().unpolish(self.btn_train)
        self.btn_train.style().polish(self.btn_train)
        self.btn_test.style().unpolish(self.btn_test)
        self.btn_test.style().polish(self.btn_test)

    def _reload_gallery(self) -> None:
        self.gallery.clear()
    
        paths = _collect_split_paths(self._split)
        query = self.search_edit.text().strip().lower()
        if query:
            paths = [p for p in paths if query in p.stem.lower()]
    
        for p in paths:
            self.gallery.addItem(_make_gallery_item(p))
    
        self.lbl_files.setText(f"Files: {len(paths)}")

    def _sync_from_disk(self) -> None:
        cur = _split_snapshot(self._split)
        if cur == self._snapshot:
            return
        self._snapshot = cur
        self._reload_gallery()

    def _select_item(self, item: QListWidgetItem) -> None:
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        p = Path(path_str)
        self.filename_changed.emit(p.stem)
        self.image_selected.emit(path_str)

    def _open_item_preview(self, item: QListWidgetItem) -> None:
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        dlg = _PreviewDialog(Path(path_str), parent=self)
        dlg.exec()

    def reset_panel(self) -> None:
        self._sync_timer.stop()
        self._split = "train"
        self.search_edit.clear()
        self.refresh_all()

class _PreviewDialog(QDialog):
    def __init__(self, img_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(img_path.name)
        self.setModal(True)
        self.resize(520, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 12, 10, 10)
        root.setSpacing(8)

        lbl_path = QLabel(str(img_path))
        lbl_path.setObjectName("Muted")
        lbl_path.setWordWrap(True)

        viewer = QLabel()
        viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viewer.setMinimumSize(420, 420)

        reader = QImageReader(str(img_path))
        reader.setAutoTransform(True)
        img = reader.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img).scaled(
                420,
                420,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            viewer.setPixmap(pm)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)

        root.addWidget(lbl_path)
        root.addWidget(viewer, 1)
        root.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignRight)


class DrawCenterCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CenterStack")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(f"""
            QFrame#CenterStack{{
                background: #000000;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        self.pill_filename = _PillLabel("Select mode")
        top_row.addStretch(1)
        top_row.addWidget(self.pill_filename, 0, Qt.AlignmentFlag.AlignCenter)
        top_row.addStretch(1)

        self.canvas = DrawCanvas()
        self.canvas.setFixedSize(CANVAS_SIZE, CANVAS_SIZE)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(10)

        self.btn_grid = _PillButton("Grid", icon=_make_grid_icon(18))
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.toggled.connect(self.canvas.set_grid_enabled)

        self.btn_undo = _PillButton("Undo", icon=_make_undo_icon(18))
        self.btn_redo = _PillButton("Redo", icon=_make_redo_icon(18))

        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_redo.clicked.connect(self.canvas.redo)

        bottom_row.addWidget(self.btn_grid, 0, Qt.AlignmentFlag.AlignLeft)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.btn_undo, 0, Qt.AlignmentFlag.AlignRight)
        bottom_row.addWidget(self.btn_redo, 0, Qt.AlignmentFlag.AlignRight)

        root.addLayout(top_row, 0)
        root.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addLayout(bottom_row, 0)

    def set_filename(self, name: str) -> None:
        self.pill_filename.setText(name)

    def sizeHint(self) -> QSize:
        return QSize(CENTER_CARD_W, 720)

    def reset_panel(self) -> None:
        self.pill_filename.setText("Select mode")
        self.canvas.reset_canvas()
        self.btn_grid.setChecked(True)

class DrawCanvas(QWidget):
    color_used = pyqtSignal()
    color_picked = pyqtSignal(QColor)
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CanvasView")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        self._loaded_image: Optional[QImage] = None
        self._canvas_image: Optional[QImage] = None

        self._brush_color = QColor("#FFFFFF")
        self._cells = CANVAS_CELLS
        
        self._active_tool = "brush"
        self._brush_shape = "circle"
        self._brush_mode = "pixel"

        self._undo_stack: list[tuple[QImage, str, QColor]] = []
        self._redo_stack: list[tuple[QImage, str, QColor]] = []
        self._stroke_before: Optional[tuple[QImage, str, QColor]] = None
        self._stroke_dirty = False

        self._brush_size = 1
        self._eraser_size = 1
        
        self._drawing = False
        self._last_point = QPoint()

        self._background_mode = "transparent"
        self._background_color = QColor("#000000")

        self.grid_enabled = True

        self._zoom = 1.0
        self._zoom_min = 1.0
        self._zoom_max = 4.0

        self._pan = QPoint(0, 0)
        self._dragging = False
        self._drag_start = QPoint(0, 0)
        self._pan_start = QPoint(0, 0)

        self.clear_image()

    def set_active_tool(self, tool: str) -> None:
        self._active_tool = tool

    def set_brush_shape(self, shape: str) -> None:
        self._brush_shape = shape

    def set_brush_mode(self, mode: str) -> None:
        self._brush_mode = mode

    def _push_undo_snapshot(self, image: QImage, bg_mode: str, bg_color: QColor) -> None:
        self._undo_stack.append((image.copy(), bg_mode, QColor(bg_color)))
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)

    def undo(self) -> None:
        if self._canvas_image is None or not self._undo_stack:
            return

        self._redo_stack.append((
            self._canvas_image.copy(),
            self._background_mode,
            QColor(self._background_color),
        ))

        img, bg_mode, bg_color = self._undo_stack.pop()
        self._canvas_image = img
        self._background_mode = bg_mode
        self._background_color = QColor(bg_color)

        self._drawing = False
        self._last_point = QPoint(-1, -1)
        self.update()

    def redo(self) -> None:
        if self._canvas_image is None or not self._redo_stack:
            return

        self._undo_stack.append((
            self._canvas_image.copy(),
            self._background_mode,
            QColor(self._background_color),
        ))

        img, bg_mode, bg_color = self._redo_stack.pop()
        self._canvas_image = img
        self._background_mode = bg_mode
        self._background_color = QColor(bg_color)

        self._drawing = False
        self._last_point = QPoint(-1, -1)
        self.update()

    def _pick_color_at_cell(self, cell: QPoint) -> None:
        if self._canvas_image is None:
            return
        if cell.x() < 0 or cell.y() < 0:
            return

        c = QColor(self._canvas_image.pixelColor(cell.x(), cell.y()))
        if c.alpha() == 0:
            return

        self._brush_color = QColor(c)
        self.color_picked.emit(QColor(c))
        self.color_used.emit()

    def set_brush_size(self, value: int) -> None:
        self._brush_size = max(1, value)

    def set_eraser_size(self, value: int) -> None:
        self._eraser_size = max(1, value)

    def reset_canvas(self) -> None:
        self._loaded_image = None
        self._zoom = 1.0
        self._pan = QPoint(0, 0)
        self._dragging = False
        self._drawing = False
        self._last_point = QPoint(-1, -1)
        self._active_tool = "brush"
        self._brush_shape = "circle"
        self._brush_size = 1
        self._eraser_size = 1
        self._background_mode = "transparent"
        self._background_color = QColor("#000000")
        self._brush_mode = "pixel"
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._stroke_before = None
        self._stroke_dirty = False
        self.clear_image()

    def sizeHint(self) -> QSize:
        return QSize(CANVAS_SIZE, CANVAS_SIZE)

    def _widget_pos_to_cell(self, pos: QPoint) -> QPoint:
        r = self._square_rect().adjusted(1, 1, -2, -2)
        center = r.center()
    
        scale = self._content_scale(self._zoom)
        content_px = int(round(self._cells * scale))
        content_rect = QRect(0, 0, content_px, content_px)
        content_rect.moveCenter(center + self._pan)
    
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return QPoint(-1, -1)
    
        x = pos.x()
        y = pos.y()
    
        if not content_rect.contains(x, y):
            return QPoint(-1, -1)
    
        rel_x = (x - content_rect.left()) / max(1, content_rect.width())
        rel_y = (y - content_rect.top()) / max(1, content_rect.height())
    
        cx = int(rel_x * self._cells)
        cy = int(rel_y * self._cells)
    
        cx = max(0, min(self._cells - 1, cx))
        cy = max(0, min(self._cells - 1, cy))
    
        return QPoint(cx, cy)

    def _draw_cell(self, cell: QPoint) -> None:
        if self._canvas_image is None:
            return
        if cell.x() < 0 or cell.y() < 0:
            return

        size = self._eraser_size if self._active_tool == "eraser" else self._brush_size
        radius = max(0, (size - 1) // 2)

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x = cell.x() + dx
                y = cell.y() + dy

                if x < 0 or y < 0 or x >= self._cells or y >= self._cells:
                    continue

                if self._brush_shape == "circle" and dx * dx + dy * dy > radius * radius:
                    continue

                if self._active_tool == "eraser":
                    self._canvas_image.setPixelColor(x, y, QColor(0, 0, 0, 0))
                    continue

                if self._brush_mode == "smooth":
                    dist2 = dx * dx + dy * dy
                    max_dist2 = max(1, radius * radius if radius > 0 else 1)
                    falloff = 1.0 - min(1.0, dist2 / max_dist2)
                    alpha = max(32, min(255, int(round(255 * falloff))))

                    src = QColor(self._canvas_image.pixelColor(x, y))
                    out = QColor(self._brush_color)
                    out.setAlpha(max(src.alpha(), alpha))
                    self._canvas_image.setPixelColor(x, y, out)
                else:
                    self._canvas_image.setPixelColor(x, y, QColor(self._brush_color))

    def _draw_line_cells(self, a: QPoint, b: QPoint) -> None:
        if a.x() < 0 or a.y() < 0 or b.x() < 0 or b.y() < 0:
            return

        dx = b.x() - a.x()
        dy = b.y() - a.y()
        steps = max(abs(dx), abs(dy), 1)

        for i in range(steps + 1):
            t = i / steps
            x = round(a.x() + dx * t)
            y = round(a.y() + dy * t)
            self._draw_cell(QPoint(x, y))


    def load_image(self, path: str) -> None:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
    
        if img.isNull():
            self._loaded_image = None
            self._canvas_image = None
            self.update()
            return
    
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        img = img.scaled(
            self._cells,
            self._cells,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    
        self._loaded_image = img
        self._canvas_image = img.copy()
        self._drawing = False
        self._last_point = QPoint(-1, -1)
        self.update()

    def clear_image(self) -> None:
        self._loaded_image = None
        self._canvas_image = QImage(self._cells, self._cells, QImage.Format.Format_RGBA8888)
        self._canvas_image.fill(Qt.GlobalColor.transparent)
        self._drawing = False
        self._last_point = QPoint(-1, -1)
        self.update()
    
    def _ensure_canvas(self) -> None:
        if self._canvas_image is None:
            self._canvas_image = QImage(self._cells, self._cells, QImage.Format.Format_RGBA8888)
            self._canvas_image.fill(Qt.GlobalColor.transparent)

    def has_image_data(self) -> bool:
        if self._canvas_image is None or self._canvas_image.isNull():
            return False

        img = self._canvas_image
        w = img.width()
        h = img.height()

        for y in range(h):
            for x in range(w):
                if QColor(img.pixelColor(x, y)).alpha() > 0:
                    return True
        return False

    def export_image(self) -> Optional[QImage]:
        if self._canvas_image is None or self._canvas_image.isNull():
            return None
        return self._canvas_image.copy()

    def set_brush_color(self, color: QColor) -> None:
        self._brush_color = QColor(color)

    def set_background_mode(self, mode: str) -> None:
        self._background_mode = mode
        self.update()

    def set_background_hex(self, text: str) -> None:
        color = _parse_hex_rgba(text)
        if not color.isValid():
            return

        if self._canvas_image is not None:
            self._push_undo_snapshot(
                self._canvas_image,
                self._background_mode,
                self._background_color,
            )
            self._redo_stack.clear()

        self._background_color = color
        if self._background_mode in ("rgb", "rgba"):
            self.update()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            gesture_type = event.gestureType()

            if gesture_type == Qt.NativeGestureType.ZoomNativeGesture:
                value = event.value()

                factor = 1.0 + value
                if factor <= 0.0:
                    factor = 0.01

                new_zoom = self._zoom * factor
                new_zoom = max(self._zoom_min, min(self._zoom_max, new_zoom))

                if new_zoom != self._zoom:
                    pos = event.position().toPoint()

                    old_scale = self._content_scale(self._zoom)
                    new_scale = self._content_scale(new_zoom)

                    center = self._square_rect().center()
                    rel = pos - center - self._pan

                    if old_scale > 1e-6:
                        content = QPointF(rel.x() / old_scale, rel.y() / old_scale)
                        new_rel = QPoint(
                            int(content.x() * new_scale),
                            int(content.y() * new_scale),
                        )
                        self._pan = pos - center - new_rel

                    self._zoom = new_zoom
                    self._clamp_pan()
                    self.update()

                return True

        return super().event(event)

    def set_grid_enabled(self, enabled: bool) -> None:
        self.grid_enabled = enabled
        self.update()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return

            factor = 1.25 if delta > 0 else 0.8
            new_zoom = max(self._zoom_min, min(self._zoom_max, self._zoom * factor))

            if new_zoom != self._zoom:
                mouse = event.position().toPoint()
                old_scale = self._content_scale(self._zoom)
                new_scale = self._content_scale(new_zoom)

                center = self._square_rect().center()
                rel = mouse - center - self._pan

                if old_scale > 1e-6:
                    content = QPointF(rel.x() / old_scale, rel.y() / old_scale)
                    new_rel = QPoint(
                        int(content.x() * new_scale),
                        int(content.y() * new_scale),
                    )
                    self._pan = mouse - center - new_rel

                self._zoom = new_zoom
                self._clamp_pan()
                self.update()

            event.accept()
            return

        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        if self._zoom > 1.0:
            self._dragging = True
            self._drag_start = event.position().toPoint()
            self._pan_start = QPoint(self._pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        self._ensure_canvas()

        cell = self._widget_pos_to_cell(event.position().toPoint())
        if cell.x() < 0 or cell.y() < 0:
            event.accept()
            return

        if self._active_tool == "picker":
            self._pick_color_at_cell(cell)
            self.update()
            event.accept()
            return

        self._stroke_before = (
            self._canvas_image.copy(),
            self._background_mode,
            QColor(self._background_color),
        )
        self._stroke_dirty = False

        self._drawing = True
        self._last_point = cell
        self._draw_cell(cell)
        self._stroke_dirty = True

        self.update()
        self.color_used.emit()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            cur = event.position().toPoint()
            delta = cur - self._drag_start
            self._pan = self._pan_start + delta
            self._clamp_pan()
            self.update()
            event.accept()
            return

        if self._active_tool == "picker":
            event.accept()
            return

        if self._drawing and self._canvas_image is not None:
            current_cell = self._widget_pos_to_cell(event.position().toPoint())

            if current_cell.x() >= 0 and current_cell.y() >= 0:
                self._draw_line_cells(self._last_point, current_cell)
                self._last_point = current_cell
                self._stroke_dirty = True
                self.update()

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.unsetCursor()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False

            if self._stroke_dirty and self._stroke_before is not None:
                img, bg_mode, bg_color = self._stroke_before
                self._push_undo_snapshot(img, bg_mode, bg_color)
                self._redo_stack.clear()

            self._stroke_before = None
            self._stroke_dirty = False

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._dragging:
            self.unsetCursor()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._background_mode in ("rgb", "rgba"):
            p.fillRect(self.rect(), self._background_color)
        else:
            p.fillRect(self.rect(), QColor(0, 0, 0))

        r = self._square_rect().adjusted(1, 1, -2, -2)
        center = r.center()

        scale = self._content_scale(self._zoom)
        content_px = int(round(self._cells * scale))
        content_rect = QRect(0, 0, content_px, content_px)
        content_rect.moveCenter(center + self._pan)

        source = self._canvas_image if self._canvas_image is not None else self._loaded_image

        if source is not None:
           iw = source.width()
           ih = source.height()

           if iw > 0 and ih > 0:
               cell_w = content_rect.width() / float(iw)
               cell_h = content_rect.height() / float(ih)

               for y in range(ih):
                   for x in range(iw):
                       c = QColor(source.pixelColor(x, y))
                       if c.alpha() == 0:
                           continue

                       x0 = int(round(content_rect.left() + x * cell_w))
                       y0 = int(round(content_rect.top() + y * cell_h))
                       x1 = int(round(content_rect.left() + (x + 1) * cell_w))
                       y1 = int(round(content_rect.top() + (y + 1) * cell_h))
                       p.fillRect(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)), c)

        frame_pen = QPen(QColor(255, 255, 255, 85))
        frame_pen.setWidth(2)
        p.setPen(frame_pen)
        p.drawRect(r)

        if self.grid_enabled:
            p.save()

            clip_rect = r.adjusted(2, 2, -2, -2)
            p.setClipRect(clip_rect)

            minor = QPen(QColor(255, 255, 255, GRID_MINOR_A))
            minor.setWidth(1)

            major = QPen(QColor(255, 255, 255, GRID_MAJOR_A))
            major.setWidth(1)

            cell_w = content_rect.width() / self._cells
            cell_h = content_rect.height() / self._cells

            for i in range(1, self._cells):
                x = int(round(content_rect.left() + i * cell_w))
                p.setPen(major if (i % 4 == 0) else minor)
                p.drawLine(x, clip_rect.top(), x, clip_rect.bottom())

            for i in range(1, self._cells):
                y = int(round(content_rect.top() + i * cell_h))
                p.setPen(major if (i % 4 == 0) else minor)
                p.drawLine(clip_rect.left(), y, clip_rect.right(), y)

            p.restore()

        p.end()

    def _square_rect(self) -> QRect:
        side = min(self.width(), self.height())
        x = (self.width() - side) // 2
        y = (self.height() - side) // 2
        return QRect(x, y, side, side)

    def _content_scale(self, zoom: float) -> float:
        r = self._square_rect()
        pad = 0
        usable = max(1, r.width() - pad * 2)
        base = usable / float(self._cells)
        return base * zoom

    def _clamp_pan(self) -> None:
        r = self._square_rect()
        scale = self._content_scale(self._zoom)
        content_px = int(self._cells * scale)

        max_shift = max(0, (content_px - r.width()) // 2)
        if max_shift <= 0:
            self._pan = QPoint(0, 0)
            return

        self._pan = QPoint(
            max(-max_shift, min(max_shift, self._pan.x())),
            max(-max_shift, min(max_shift, self._pan.y())),
        )

class _ToolPopup(QWidget):
    option_selected = pyqtSignal(str)

    def __init__(self, icons: list[QIcon], values: list[str]) -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Popup
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("ToolPopupFrame")
        frame.setStyleSheet("""
            QFrame#ToolPopupFrame {
                background: #000000;
                border: 1px solid rgba(255,255,255,60);
                border-radius: 16px;
            }
            QToolButton#ToolPopupButton {
                min-width: 54px;
                max-width: 54px;
                min-height: 54px;
                max-height: 54px;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,42);
                background: #0A0A0A;
                padding: 0;
            }
            QToolButton#ToolPopupButton:hover {
                border: 1px solid rgba(255,255,255,95);
                background: #101010;
            }
        """)

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        for icon, val in zip(icons, values):
            b = QToolButton()
            b.setObjectName("ToolPopupButton")
            b.setIcon(icon)
            b.setIconSize(QSize(34, 34))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, v=val: self._pick(v))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)

        root.addWidget(frame)

    def _pick(self, val: str) -> None:
        self.option_selected.emit(val)
        self.close()

class _RgbBackgroundPopup(QWidget):
    done_clicked = pyqtSignal(str)

    def __init__(self, *, initial_hex: str = "#000000") -> None:
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Popup
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("RgbBackgroundPopupFrame")
        frame.setStyleSheet("""
            QFrame#RgbBackgroundPopupFrame {
                background: #050505;
                border: 1px solid rgba(255,255,255,40);
                border-radius: 16px;
            }
            QLineEdit#PopupBgHexEdit {
                min-height: 34px;
                max-height: 34px;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                border-radius: 10px;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 600;
                padding: 0 10px;
            }
            QLineEdit#PopupBgHexEdit:focus {
                border: 1px solid rgba(255,255,255,90);
            }
            QPushButton#PopupDoneButton {
                min-height: 34px;
                max-height: 34px;
                border-radius: 10px;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 800;
                padding: 0 12px;
            }
            QPushButton#PopupDoneButton:hover {
                border: 1px solid rgba(255,255,255,90);
                background: #101010;
            }
        """)

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        self.hex_edit = QLineEdit()
        self.hex_edit.setObjectName("PopupBgHexEdit")
        self.hex_edit.setText(initial_hex)
        self.hex_edit.setPlaceholderText("#000000")
        self.hex_edit.setMaxLength(9)
        self.hex_edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression("^#?[0-9A-Fa-f]{0,8}$"),
                self.hex_edit,
            )
        )

        self.btn_done = QPushButton("Done")
        self.btn_done.setObjectName("PopupDoneButton")
        self.btn_done.clicked.connect(self._emit_done)

        lay.addWidget(self.hex_edit, 1)
        lay.addWidget(self.btn_done, 0)

        root.addWidget(frame)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.hex_edit.setFocus()
        self.hex_edit.selectAll()

    def _emit_done(self) -> None:
        text = self.hex_edit.text().strip()
        if not text:
            return

        color = _parse_hex_rgba(text)
        if not color.isValid():
            return

        self.done_clicked.emit(_color_to_hex_rgba(color))
        self.close()

class _ToolOptionsCard(QFrame):
    brush_mode_changed = pyqtSignal(str)
    brush_shape_changed = pyqtSignal(str)
    active_tool_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ToolOptionsCard")

        self._brush_mode = "pixel"
        self._brush_shape = "circle"
        self._active_tool = "brush"

        self._icon_pixel = _load_icon(PIXEL_BRUSH_ICON)
        self._icon_smooth = _load_icon(SMOOTH_BRUSH_ICON)
        self._icon_circle = _load_icon(CIRCLE_BRUSH_ICON)
        self._icon_square = _load_icon(SQUARE_BRUSH_ICON)
        self._icon_eraser = _load_icon(ERASER_ICON)
        self._icon_picker = _load_icon(COLOR_PICKER_ICON)

        self.setStyleSheet(f"""
            QFrame#ToolOptionsCard {{
                background: #050505;
                border: 1px solid rgba(255,255,255,40);
                border-radius: 18px;
            }}
            QLabel#ToolCardTitle {{
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 700;
            }}
            QToolButton#ToolTile {{
                min-width: 58px;
                max-width: 58px;
                min-height: 58px;
                max-height: 58px;
                border-radius: 12px;
                padding: 0;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
            }}
            QToolButton#ToolTile:hover {{
                border: 1px solid rgba(255,255,255,85);
                background: #0D0D0D;
            }}
            QToolButton#ToolTile[active="true"] {{
                background: rgba(255,255,255,14);
                border: 1px solid rgba(255,255,255,110);
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("Tools")
        title.setObjectName("ToolCardTitle")

        stack_wrap = QWidget()
        stack = QVBoxLayout(stack_wrap)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(8)

        self.btn_brush_mode = QToolButton()
        self.btn_brush_mode.setObjectName("ToolTile")
        self.btn_brush_mode.setProperty("active", True)
        self.btn_brush_mode.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_brush_mode.setIconSize(QSize(38, 38))
        self.btn_brush_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_brush_mode.clicked.connect(self._open_brush_menu)

        self.btn_brush_shape = QToolButton()
        self.btn_brush_shape.setObjectName("ToolTile")
        self.btn_brush_shape.setProperty("active", False)
        self.btn_brush_shape.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_brush_shape.setIconSize(QSize(38, 38))
        self.btn_brush_shape.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_brush_shape.clicked.connect(self._open_shape_menu)

        self.btn_eraser = QToolButton()
        self.btn_eraser.setObjectName("ToolTile")
        self.btn_eraser.setProperty("active", False)
        self.btn_eraser.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_eraser.setIcon(self._icon_eraser)
        self.btn_eraser.setIconSize(QSize(38, 38))
        self.btn_eraser.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eraser.clicked.connect(lambda: self._set_active_tool("eraser"))

        self.btn_picker = QToolButton()
        self.btn_picker.setObjectName("ToolTile")
        self.btn_picker.setProperty("active", False)
        self.btn_picker.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_picker.setIcon(self._icon_picker)
        self.btn_picker.setIconSize(QSize(38, 38))
        self.btn_picker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_picker.clicked.connect(lambda: self._set_active_tool("picker"))

        stack.addWidget(self.btn_brush_mode, 0, Qt.AlignmentFlag.AlignHCenter)
        stack.addWidget(self.btn_brush_shape, 0, Qt.AlignmentFlag.AlignHCenter)
        stack.addWidget(self.btn_eraser, 0, Qt.AlignmentFlag.AlignHCenter)
        stack.addWidget(self.btn_picker, 0, Qt.AlignmentFlag.AlignHCenter)

        root.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(stack_wrap, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

        self._refresh_brush_mode_button()
        self._refresh_brush_shape_button()
        self._refresh_active_tool_buttons()

    def reset_panel(self) -> None:
        self._brush_mode = "pixel"
        self._brush_shape = "circle"
        self._active_tool = "brush"
        self._refresh_brush_mode_button()
        self._refresh_brush_shape_button()
        self._refresh_active_tool_buttons()
        self.active_tool_changed.emit("brush")
        self.brush_shape_changed.emit("circle")
        self.brush_mode_changed.emit("pixel")

    def brush_mode(self) -> str:
        return self._brush_mode

    def brush_shape(self) -> str:
        return self._brush_shape

    def active_tool(self) -> str:
        return self._active_tool

    def _open_brush_menu(self) -> None:
        icons = [
            self._icon_pixel,
            self._icon_smooth,
        ]
        values = [
            "pixel",
            "smooth",
        ]

        self._brush_popup = _ToolPopup(icons, values)
        self._brush_popup.option_selected.connect(self._set_brush_mode)

        pos = self.btn_brush_mode.mapToGlobal(self.btn_brush_mode.rect().topLeft())
        self._brush_popup.adjustSize()
        self._brush_popup.move(
            pos.x() - self._brush_popup.width() - 8,
            pos.y(),
        )
        self._brush_popup.show()

    def _set_brush_mode(self, mode: str) -> None:
        self._brush_mode = mode
        self._set_active_tool("brush")
        self._refresh_brush_mode_button()
        self.brush_mode_changed.emit(self._brush_mode)

    def _open_shape_menu(self) -> None:
        icons = [
            self._icon_circle,
            self._icon_square,
        ]
        values = [
            "circle",
            "square",
        ]

        self._shape_popup = _ToolPopup(icons, values)
        self._shape_popup.option_selected.connect(self._set_brush_shape)

        pos = self.btn_brush_shape.mapToGlobal(self.btn_brush_shape.rect().topLeft())
        self._shape_popup.adjustSize()
        self._shape_popup.move(
            pos.x() - self._shape_popup.width() - 8,
            pos.y(),
        )
        self._shape_popup.show()

    def _set_brush_shape(self, shape: str) -> None:
        self._brush_shape = shape
        self._refresh_brush_shape_button()
        self.brush_shape_changed.emit(self._brush_shape)

    def _set_active_tool(self, tool: str) -> None:
        self._active_tool = tool
        self._refresh_active_tool_buttons()
        self.active_tool_changed.emit(tool)

    def _refresh_brush_mode_button(self) -> None:
        self.btn_brush_mode.setIcon(
            self._icon_smooth if self._brush_mode == "smooth" else self._icon_pixel
        )

    def _refresh_brush_shape_button(self) -> None:
        self.btn_brush_shape.setIcon(
            self._icon_square if self._brush_shape == "square" else self._icon_circle
        )

    def _refresh_active_tool_buttons(self) -> None:
        brush_active = self._active_tool == "brush"

        self.btn_brush_mode.setProperty("active", brush_active)
        self.btn_brush_shape.setProperty("active", brush_active)
        self.btn_eraser.setProperty("active", self._active_tool == "eraser")
        self.btn_picker.setProperty("active", self._active_tool == "picker")

        for btn in (
            self.btn_brush_mode,
            self.btn_brush_shape,
            self.btn_eraser,
            self.btn_picker,
        ):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

class _BrushSettingsCard(QFrame):
    brush_size_changed = pyqtSignal(int)
    eraser_size_changed = pyqtSignal(int)
    background_mode_changed = pyqtSignal(str)
    background_hex_changed = pyqtSignal(str)
    background_done_clicked = pyqtSignal(str)

    def reset_panel(self) -> None:
        self.brush_slider.blockSignals(True)
        self.eraser_slider.blockSignals(True)

        self.brush_slider.setValue(10)
        self.eraser_slider.setValue(8)

        self.brush_slider.blockSignals(False)
        self.eraser_slider.blockSignals(False)

        self.lbl_brush_px.setText("10 px")
        self.lbl_eraser_px.setText("8 px")

        self._background_mode = "transparent"
        self._rgb_edit_open = False
        self._applied_background_hex = "#000000"

        self.btn_bg_transparent.setProperty("active", True)
        self.btn_bg_rgb.setProperty("active", False)

        self.btn_bg_transparent.style().unpolish(self.btn_bg_transparent)
        self.btn_bg_transparent.style().polish(self.btn_bg_transparent)
        self.btn_bg_rgb.style().unpolish(self.btn_bg_rgb)
        self.btn_bg_rgb.style().polish(self.btn_bg_rgb)

        self._update_background_indicator()

        self.brush_size_changed.emit(10)
        self.eraser_size_changed.emit(8)
        self.background_mode_changed.emit("transparent")

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BrushSettingsCard")

        self._brush_icon = _load_icon(PIXEL_BRUSH_ICON)
        self._eraser_icon = _load_icon(ERASER_ICON)

        self._background_mode = "transparent"
        self._rgb_edit_open = False
        self._applied_background_hex = "#000000"

        self.setStyleSheet(f"""
            QFrame#BrushSettingsCard {{
                background: #050505;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QLabel#SettingsTitle {{
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#SettingsValue {{
                color: rgba(255,255,255,235);
                font-size: 15px;
                font-weight: 700;
            }}
            QLabel#MiniLabel {{
                color: rgba(255,255,255,210);
                font-size: 13px;
                font-weight: 700;
            }}
            QFrame#IconTile {{
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                border-radius: 12px;
            }}
            QPushButton#BgModeButton {{
                min-height: 48px;
                border-radius: 14px;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                color: rgba(255,255,255,220);
                font-size: 15px;
                font-weight: 700;
                padding: 0 14px;
            }}
            QPushButton#BgModeButton:hover {{
                border: 1px solid rgba(255,255,255,78);
                background: #0D0D0D;
            }}
            QPushButton#BgModeButton[active="true"] {{
                background: rgba(255,255,255,14);
                border: 1px solid rgba(255,255,255,110);
                color: rgba(255,255,255,255);
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("Tools")
        title.setObjectName("SettingsTitle")

        # Brush size row
        brush_row = QHBoxLayout()
        brush_row.setContentsMargins(0, 0, 0, 0)
        brush_row.setSpacing(10)

        self.brush_tile = _SettingsIconTile(self._brush_icon)
        self.brush_tile.setFixedSize(52, 52)

        self.brush_slider = _SoftSizeSlider(Qt.Orientation.Horizontal)
        self.brush_slider.setObjectName("SizeSlider")
        self.brush_slider.setRange(1, 16)
        self.brush_slider.setValue(10)
        self.brush_slider.valueChanged.connect(self._on_brush_size_changed)

        self.lbl_brush_px = QLabel("10 px")
        self.lbl_brush_px.setObjectName("SettingsValue")
        self.lbl_brush_px.setFixedWidth(48)

        brush_row.addWidget(self.brush_tile, 0)
        brush_row.addWidget(self.brush_slider, 1)
        brush_row.addWidget(self.lbl_brush_px, 0)

        # Eraser size row
        eraser_row = QHBoxLayout()
        eraser_row.setContentsMargins(0, 0, 0, 0)
        eraser_row.setSpacing(10)

        self.eraser_tile = _SettingsIconTile(self._eraser_icon)
        self.eraser_tile.setFixedSize(52, 52)

        self.eraser_slider = _SoftSizeSlider(Qt.Orientation.Horizontal)
        self.eraser_slider.setObjectName("SizeSlider")
        self.eraser_slider.setRange(1, 16)
        self.eraser_slider.setValue(8)
        self.eraser_slider.valueChanged.connect(self._on_eraser_size_changed)

        self.lbl_eraser_px = QLabel("8 px")
        self.lbl_eraser_px.setObjectName("SettingsValue")
        self.lbl_eraser_px.setFixedWidth(48)

        eraser_row.addWidget(self.eraser_tile, 0)
        eraser_row.addWidget(self.eraser_slider, 1)
        eraser_row.addWidget(self.lbl_eraser_px, 0)

        bg_label_row = QHBoxLayout()
        bg_label_row.setContentsMargins(0, 0, 0, 0)
        bg_label_row.setSpacing(8)

        bg_label = QLabel("Background")
        bg_label.setObjectName("MiniLabel")

        self.bg_indicator = QLabel("Transparent")
        self.bg_indicator.setObjectName("MiniLabel")

        bg_label_row.addWidget(bg_label, 0, Qt.AlignmentFlag.AlignLeft)
        bg_label_row.addStretch(1)
        bg_label_row.addWidget(self.bg_indicator, 0, Qt.AlignmentFlag.AlignRight)

        bg_mode_row = QHBoxLayout()
        bg_mode_row.setContentsMargins(0, 0, 0, 0)
        bg_mode_row.setSpacing(10)

        self.btn_bg_transparent = QPushButton("Transparent")
        self.btn_bg_transparent.setObjectName("BgModeButton")
        self.btn_bg_transparent.setProperty("active", True)
        self.btn_bg_transparent.clicked.connect(lambda: self._set_background_mode("transparent"))

        self.btn_bg_rgb = QPushButton("RGB")
        self.btn_bg_rgb.setObjectName("BgModeButton")
        self.btn_bg_rgb.setProperty("active", False)
        self.btn_bg_rgb.clicked.connect(lambda: self._set_background_mode("rgb"))

        bg_mode_row.addWidget(self.btn_bg_transparent, 1)
        bg_mode_row.addWidget(self.btn_bg_rgb, 1)

        root.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)
        root.addLayout(brush_row)
        root.addLayout(eraser_row)
        root.addLayout(bg_label_row)
        root.addLayout(bg_mode_row)

        self._update_background_indicator()

    def set_brush_icon_mode(self, mode: str) -> None:
        self._brush_icon = _load_icon(SMOOTH_BRUSH_ICON if mode == "smooth" else PIXEL_BRUSH_ICON)
        self.brush_tile.set_icon(self._brush_icon)

    def _update_background_indicator(self) -> None:
        if self._background_mode == "transparent":
            self.bg_indicator.setText("Transparent")
            return

        color = _parse_hex_rgba(self._applied_background_hex)
        if color.isValid() and color.alpha() < 255:
            self.bg_indicator.setText(f"RGBA {self._applied_background_hex}")
        else:
            self.bg_indicator.setText(f"RGB {self._applied_background_hex}")

    def _on_brush_size_changed(self, value: int) -> None:
        self.lbl_brush_px.setText(f"{value} px")
        self.brush_size_changed.emit(value)

    def _on_eraser_size_changed(self, value: int) -> None:
        self.lbl_eraser_px.setText(f"{value} px")
        self.eraser_size_changed.emit(value)

    def _set_background_mode(self, mode: str) -> None:
        if mode == "transparent":
            self._background_mode = "transparent"
            self._rgb_edit_open = False
            self.background_mode_changed.emit("transparent")

            self.btn_bg_transparent.setProperty("active", True)
            self.btn_bg_rgb.setProperty("active", False)

            self.btn_bg_transparent.style().unpolish(self.btn_bg_transparent)
            self.btn_bg_transparent.style().polish(self.btn_bg_transparent)
            self.btn_bg_rgb.style().unpolish(self.btn_bg_rgb)
            self.btn_bg_rgb.style().polish(self.btn_bg_rgb)

            self._update_background_indicator()
            return

        self._open_rgb_popup()

    def _open_rgb_popup(self) -> None:
        self.btn_bg_transparent.setProperty("active", False)
        self.btn_bg_rgb.setProperty("active", True)

        self.btn_bg_transparent.style().unpolish(self.btn_bg_transparent)
        self.btn_bg_transparent.style().polish(self.btn_bg_transparent)
        self.btn_bg_rgb.style().unpolish(self.btn_bg_rgb)
        self.btn_bg_rgb.style().polish(self.btn_bg_rgb)

        initial_hex = (
            self._applied_background_hex
            if self._background_mode in ("rgb", "rgba")
            else "#000000"
        )

        self._rgb_popup = _RgbBackgroundPopup(initial_hex=initial_hex)
        self._rgb_popup.done_clicked.connect(self._apply_rgb_done)

        pos = self.mapToGlobal(self.rect().bottomLeft())
        popup_width = self.width()
        
        self._rgb_popup.setFixedWidth(popup_width)
        self._rgb_popup.adjustSize()

        self._rgb_popup.move(
            pos.x(),
            pos.y() + 2,
        )
        
        self._rgb_popup.show()

    def _apply_rgb_done(self, text: str) -> None:
        color = _parse_hex_rgba(text)

        if not color.isValid():
            return

        has_alpha = color.alpha() < 255

        self._background_mode = "rgba" if has_alpha else "rgb"
        self._rgb_edit_open = False
        self._applied_background_hex = _color_to_hex_rgba(color)

        self.background_mode_changed.emit(self._background_mode)
        self.background_done_clicked.emit(self._applied_background_hex)

        self.btn_bg_transparent.setProperty("active", False)
        self.btn_bg_rgb.setProperty("active", True)

        self.btn_bg_transparent.style().unpolish(self.btn_bg_transparent)
        self.btn_bg_transparent.style().polish(self.btn_bg_transparent)

        self.btn_bg_rgb.style().unpolish(self.btn_bg_rgb)
        self.btn_bg_rgb.style().polish(self.btn_bg_rgb)

        self._update_background_indicator()

class _SavePanelCard(QFrame):
    save_requested = pyqtSignal(int)

    def reset_panel(self) -> None:
        self._mode = None
        self._split = "train"
        self._digit = None
        self._next_index = 0
        self._filename_hint = "Select mode"
    
        self.lbl_status.setText("Ready")
        self._refresh_meta()
        self._refresh_enabled()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SavePanelCard")

        self._mode: Optional[str] = None
        self._split = "train"
        self._digit: Optional[int] = None
        self._next_index = 0
        self._filename_hint = "Select mode"

        self.setStyleSheet(f"""
            QFrame#SavePanelCard {{
                background: #050505;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QLabel#SaveTitle {{
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#SaveMeta {{
                color: rgba(255,255,255,185);
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#SaveStatus {{
                color: rgba(255,255,255,235);
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton#SaveActionButton {{
                min-height: 36px;
                border-radius: 14px;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 800;
                padding: 0 10px;
                text-align: center;
            }}
            QPushButton#SaveActionButton:hover {{
                border: 1px solid rgba(255,255,255,90);
                background: #101010;
            }}
            QPushButton#SaveActionButton:disabled {{
                color: rgba(255,255,255,90);
                border: 1px solid rgba(255,255,255,20);
                background: #080808;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Save")
        title.setObjectName("SaveTitle")

        self.lbl_target = QLabel("Target: —")
        self.lbl_target.setObjectName("SaveMeta")

        self.lbl_name = QLabel("Next: —")
        self.lbl_name.setObjectName("SaveMeta")

        self.btn_save_1 = QPushButton("Save")
        self.btn_save_1.setObjectName("SaveActionButton")
        self.btn_save_1.clicked.connect(lambda: self.save_requested.emit(1))

        self.btn_save_10 = QPushButton("Save ×10")
        self.btn_save_10.setObjectName("SaveActionButton")
        self.btn_save_10.clicked.connect(lambda: self.save_requested.emit(10))

        self.btn_save_100 = QPushButton("Save ×100")
        self.btn_save_100.setObjectName("SaveActionButton")
        self.btn_save_100.clicked.connect(lambda: self.save_requested.emit(100))

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setObjectName("SaveStatus")

        root.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.lbl_target)
        root.addWidget(self.lbl_name)
        root.addSpacing(2)
        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        batch_row.setSpacing(8)

        batch_row.addWidget(self.btn_save_10, 1)
        batch_row.addWidget(self.btn_save_100, 1)

        root.addWidget(self.btn_save_1)
        root.addLayout(batch_row)
        root.addWidget(self.lbl_status)

        self._refresh_meta()
        self._refresh_enabled()

    def set_mode(self, mode: Optional[str]) -> None:
        self._mode = mode
        self._refresh_enabled()

    def set_filename_hint(self, text: str) -> None:
        self._filename_hint = text
        self._refresh_meta()

    def set_create_state(self, state: dict) -> None:
        self._split = state.get("split", "train")
        self._digit = state.get("digit")
        self._next_index = int(state.get("next_index", 0))
        self._refresh_meta()
        self._refresh_enabled()

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _refresh_meta(self) -> None:
        if self._mode == "edit":
            self.lbl_target.setText("Target: current file")
            self.lbl_name.setText(f"Current: {self._filename_hint}")
            return

        if self._mode == "create":
            if self._split == "train":
                target = f"train / {self._digit}" if self._digit is not None else "train / ?"
                name = f"{self._digit}_{self._next_index:05d}" if self._digit is not None else "Select digit"
            else:
                target = "test"
                name = f"{self._next_index:05d}"

            self.lbl_target.setText(f"Target: {target}")
            self.lbl_name.setText(f"Next: {name}")
            return

        self.lbl_target.setText("Target: —")
        self.lbl_name.setText("Next: —")

    def _refresh_enabled(self) -> None:
        self.btn_save_1.setEnabled(self._mode in ("create", "edit"))
        self.btn_save_10.setEnabled(self._mode == "create")
        self.btn_save_100.setEnabled(self._mode == "create")

class _SettingsIconTile(QFrame):
    def __init__(self, icon: QIcon) -> None:
        super().__init__()
        self.setObjectName("IconTile")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.label)
        self.set_icon(icon)

    def set_icon(self, icon: QIcon) -> None:
        pm = icon.pixmap(34, 34)
        self.label.setPixmap(pm)

class _ColorToolsCard(QFrame):
    color_changed = pyqtSignal(QColor)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ColorToolsCard")

        self._current_color = QColor("#FFFFFF")
        self._alpha = 255
        self._recent_colors: list[str] = [
            "#000000",
            "#FFFFFF",
            "#FF3B30",
            "#34C759",
            "#0A84FF",
        ]

        self.setStyleSheet(f"""
            QFrame#ColorToolsCard {{
                background: #050505;
                border: 1px solid {BORDER_RGBA};
                border-radius: 18px;
            }}
            QLabel#ColorToolsTitle {{
                color: rgba(255,255,255,255);
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#ColorValue {{
                color: rgba(255,255,255,235);
                font-size: 16px;
                font-weight: 600;
                padding-left: 2px;
            }}
            QLineEdit#HexEdit {{
                min-height: 36px;
                background: #090909;
                border: 1px solid rgba(255,255,255,42);
                border-radius: 12px;
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 600;
                padding: 0 12px;
            }}
            QLineEdit#HexEdit:focus {{
                border: 1px solid rgba(255,255,255,90);
            }}
            QSlider#HueSlider::groove:horizontal {{
                height: 16px;
                border-radius: 8px;
                background: transparent;
                border: none;
            }}
            QSlider#HueSlider::handle:horizontal {{
                width: 12px;
                margin: -3px 0;
                border-radius: 6px;
                background: rgba(255,255,255,235);
                border: 1px solid rgba(0,0,0,180);
            }}
            QSlider#AlphaSlider::groove:horizontal {{
                height: 16px;
                border-radius: 8px;
                background: transparent;
                border: none;
            }}
            QSlider#AlphaSlider::handle:horizontal {{
                width: 12px;
                margin: -3px 0;
                border-radius: 6px;
                background: rgba(255,255,255,235);
                border: 1px solid rgba(0,0,0,180);
            }}
            QPushButton#RecentColorButton {{
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border-radius: 9px;
                border: 1px solid rgba(255,255,255,55);
                padding: 0;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("Color")
        title.setObjectName("ColorToolsTitle")

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.preview = _ColorPreviewSwatch()
        self.preview.setFixedSize(58, 58)

        recent_wrap = QWidget()
        recent_grid = QGridLayout(recent_wrap)
        recent_grid.setContentsMargins(0, 0, 0, 0)
        recent_grid.setHorizontalSpacing(6)
        recent_grid.setVerticalSpacing(6)

        self.recent_buttons: list[QPushButton] = []
        for i in range(5):
            btn = QPushButton("")
            btn.setObjectName("RecentColorButton")
            btn.clicked.connect(lambda _, idx=i: self._apply_recent(idx))
            self.recent_buttons.append(btn)
            recent_grid.addWidget(btn, 0, i)

        top_row.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(recent_wrap, 1)

        self.hex_edit = QLineEdit()
        self.hex_edit.setObjectName("HexEdit")
        self.hex_edit.setPlaceholderText("#000000")
        self.hex_edit.setMaxLength(9)
        self.hex_edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression("^#?[0-9A-Fa-f]{0,8}$"),
                self.hex_edit,
            )
        )
        self.hex_edit.editingFinished.connect(self._apply_hex)

        self.color_field = _ColorField()
        self.color_field.setFixedHeight(220)
        self.color_field.color_changed.connect(self._on_field_changed)

        self.hue_slider = _HueSlider(Qt.Orientation.Horizontal)
        self.hue_slider.setObjectName("HueSlider")
        self.hue_slider.setRange(0, 359)
        self.hue_slider.setFixedHeight(22)
        self.hue_slider.valueChanged.connect(self._on_hue_changed)
        self.alpha_slider = _SoftSizeSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setObjectName("AlphaSlider")
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(255)
        self.alpha_slider.setFixedHeight(22)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)

        self.alpha_label = QLabel("Alpha 255")
        self.alpha_label.setObjectName("Muted")

        root.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)
        root.addLayout(top_row)
        root.addWidget(self.hex_edit)
        root.addWidget(self.color_field)
        root.addWidget(self.hue_slider)
        root.addWidget(self.alpha_label)
        root.addWidget(self.alpha_slider)

        self._sync_from_color(self._current_color)
        self._refresh_recent_buttons()

    def reset_panel(self) -> None:
        self._current_color = QColor("#FFFFFF")
        self._alpha = 255
        self._recent_colors = [
            "#000000",
            "#FFFFFF",
            "#FF3B30",
            "#34C759",
            "#0A84FF",
        ]
        self._sync_from_color(self._current_color)
        self._refresh_recent_buttons()
        
        self.alpha_slider.blockSignals(True)
        self.alpha_slider.setValue(255)
        self.alpha_slider.blockSignals(False)
        self.alpha_label.setText("Alpha 255")

    def _on_alpha_changed(self, value: int) -> None:
        self._alpha = max(0, min(255, value))
        self.alpha_label.setText(f"Alpha {self._alpha}")

        color = QColor(self._current_color)
        color.setAlpha(self._alpha)
        self._set_current_color(color, push_recent=False)

    def display_hex(self) -> str:
        return _color_to_hex_rgba(self._current_color)

    def set_external_color(self, color: QColor) -> None:
        self._set_current_color(color, push_recent=False)

    def current_color(self) -> QColor:
        return QColor(self._current_color)

    def _on_field_changed(self, color: QColor) -> None:
        color.setAlpha(self._alpha)
        self._set_current_color(color, push_recent=False)

    def _on_hue_changed(self, hue: int) -> None:
        s = self.color_field.saturation()
        v = self.color_field.value()
        color = QColor.fromHsv(hue % 360, int(round(s * 255)), int(round(v * 255)))
        color.setAlpha(self._alpha)
        self.color_field.set_hue(hue % 360)
        self._set_current_color(color, push_recent=False)

    def _apply_hex(self) -> None:
        text = self.hex_edit.text().strip()
        if not text:
            self.hex_edit.setText(self.display_hex())
            return

        if not text.startswith("#"):
            text = f"#{text}"

        color = _parse_hex_rgba(text)
        if not color.isValid():
            self.hex_edit.setText(self.display_hex())
            return

        self._set_current_color(color, push_recent=False)

    def _apply_recent(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._recent_colors):
            return
        color = QColor(self._recent_colors[idx])
        if not color.isValid():
            return
        color.setAlpha(self._alpha)
        self._set_current_color(color, push_recent=False)

    def _set_current_color(self, color: QColor, *, push_recent: bool) -> None:
        if not color.isValid():
            return

        self._current_color = QColor(color)
        self._alpha = self._current_color.alpha()
        self.preview.set_color(self._current_color)
        self.hex_edit.setText(self.display_hex())

        self.alpha_slider.blockSignals(True)
        self.alpha_slider.setValue(self._alpha)
        self.alpha_slider.blockSignals(False)
        self.alpha_label.setText(f"Alpha {self._alpha}")

        self._sync_field_and_slider(self._current_color)

        if push_recent:
            self._push_recent(self._current_color.name().upper())

        self.color_changed.emit(QColor(self._current_color))

    def _sync_from_color(self, color: QColor) -> None:
        self.preview.set_color(color)
        self.hex_edit.setText(self.display_hex())
        self._sync_field_and_slider(color)
        self.color_changed.emit(QColor(color))

    def _sync_field_and_slider(self, color: QColor) -> None:
        h, s, v, _ = color.getHsv()
        if h < 0:
            h = 0

        self.hue_slider.blockSignals(True)
        self.hue_slider.setValue(h)
        self.hue_slider.blockSignals(False)

        self.color_field.blockSignals(True)
        self.color_field.set_hue(h)
        self.color_field.set_sv(s / 255.0, v / 255.0)
        self.color_field.blockSignals(False)
        self.color_field.update()

    def commit_current_color_to_history(self) -> None:
        hex_color = self._current_color.name().upper()

        if self._recent_colors and self._recent_colors[0].upper() == hex_color:
            return

        self._push_recent(hex_color)
        
    def _push_recent(self, hex_color: str) -> None:
        hex_color = hex_color.upper()
        if hex_color in self._recent_colors:
            self._recent_colors.remove(hex_color)
        self._recent_colors.insert(0, hex_color)
        self._recent_colors = self._recent_colors[:5]
        self._refresh_recent_buttons()

    def _refresh_recent_buttons(self) -> None:
        for i, btn in enumerate(self.recent_buttons):
            color = self._recent_colors[i] if i < len(self._recent_colors) else "#000000"
            btn.setStyleSheet(f"""
                QPushButton#RecentColorButton {{
                    min-width: 30px;
                    max-width: 30px;
                    min-height: 30px;
                    max-height: 30px;
                    border-radius: 9px;
                    border: 1px solid rgba(255,255,255,55);
                    background: {color};
                    padding: 0;
                }}
            """)


class _ColorPreviewSwatch(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._color = QColor("#000000")

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect().adjusted(1, 1, -1, -1)
        rf = QRectF(r)

        path = QPainterPath()
        path.addRoundedRect(rf, 12, 12)

        p.save()
        p.setClipPath(path)

        tile = 8
        p.setPen(Qt.PenStyle.NoPen)
        for y in range(r.top(), r.bottom() + 1, tile):
            for x in range(r.left(), r.right() + 1, tile):
                even = ((x - r.left()) // tile + (y - r.top()) // tile) % 2 == 0
                p.fillRect(
                    QRect(x, y, tile, tile),
                    QColor(92, 92, 92) if even else QColor(42, 42, 42),
                )

        p.fillRect(r, self._color)
        p.restore()

        pen = QPen(QColor(255, 255, 255, 80))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rf, 12, 12)

        p.end()


class _ColorField(QWidget):
    color_changed = pyqtSignal(QColor)
    interaction_finished = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._hue = 0
        self._sat = 0.0
        self._val = 0.0
        self.setMinimumHeight(180)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hue(self, hue: int) -> None:
        self._hue = int(max(0, min(359, hue)))
        self.update()

    def set_sv(self, sat: float, val: float) -> None:
        self._sat = max(0.0, min(1.0, sat))
        self._val = max(0.0, min(1.0, val))
        self.update()

    def saturation(self) -> float:
        return self._sat

    def value(self) -> float:
        return self._val

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._update_from_pos(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_from_pos(event.position().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.interaction_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _inner_rect(self) -> QRect:
        return self.rect().adjusted(1, 1, -2, -2)

    def _update_from_pos(self, pos: QPoint) -> None:
        r = self._inner_rect()
        w = max(1, r.width() - 1)
        h = max(1, r.height() - 1)

        x = max(r.left(), min(r.right(), pos.x()))
        y = max(r.top(), min(r.bottom(), pos.y()))

        self._sat = (x - r.left()) / float(w)
        self._val = 1.0 - ((y - r.top()) / float(h))

        self._sat = max(0.0, min(1.0, self._sat))
        self._val = max(0.0, min(1.0, self._val))

        color = QColor.fromHsv(
            self._hue,
            int(round(self._sat * 255)),
            int(round(self._val * 255)),
        )
        self.color_changed.emit(color)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self._inner_rect()
        rf = QRectF(r)

        path = QPainterPath()
        path.addRoundedRect(rf, 14, 14)

        p.save()
        p.setClipPath(path)

        hue_color = QColor.fromHsv(self._hue, 255, 255)

        grad_x = QLinearGradient(
            QPointF(r.left(), r.top()),
            QPointF(r.right(), r.top()),
        )
        grad_x.setColorAt(0.0, QColor("#FFFFFF"))
        grad_x.setColorAt(1.0, hue_color)
        p.fillRect(r, grad_x)

        grad_y = QLinearGradient(
            QPointF(r.left(), r.top()),
            QPointF(r.left(), r.bottom()),
        )
        grad_y.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_y.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(r, grad_y)

        p.restore()

        pen = QPen(QColor(255, 255, 255, 70))
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rf, 14, 14)

        px = int(round(r.left() + self._sat * (r.width() - 1)))
        py = int(round(r.top() + (1.0 - self._val) * (r.height() - 1)))

        outer = QPen(QColor(0, 0, 0, 230))
        outer.setWidth(3)
        p.setPen(outer)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPoint(px, py), 7, 7)

        inner = QPen(QColor(255, 255, 255, 245))
        inner.setWidth(2)
        p.setPen(inner)
        p.drawEllipse(QPoint(px, py), 7, 7)

        p.end()

class _HueSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation) -> None:
        super().__init__(orientation)
        self.setTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _groove_rect(self) -> QRect:
        return self.rect().adjusted(6, 4, -6, -4)

    def _set_value_from_pos(self, x: float) -> None:
        groove = self._groove_rect()
        if groove.width() <= 1:
            return

        pos = max(groove.left(), min(groove.right(), int(round(x))))
        ratio = (pos - groove.left()) / max(1.0, float(groove.width() - 1))
        value = self.minimum() + ratio * (self.maximum() - self.minimum())
        self.setValue(int(round(value)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_value_from_pos(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_value_from_pos(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        groove = self._groove_rect()

        grad = QLinearGradient(
            QPointF(groove.left(), groove.top()),
            QPointF(groove.right(), groove.top()),
        )
        grad.setColorAt(0.00, QColor.fromHsv(0, 255, 255))
        grad.setColorAt(0.16, QColor.fromHsv(60, 255, 255))
        grad.setColorAt(0.33, QColor.fromHsv(120, 255, 255))
        grad.setColorAt(0.50, QColor.fromHsv(180, 255, 255))
        grad.setColorAt(0.66, QColor.fromHsv(240, 255, 255))
        grad.setColorAt(0.83, QColor.fromHsv(300, 255, 255))
        grad.setColorAt(1.00, QColor.fromHsv(359, 255, 255))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(groove, 8, 8)

        border = QPen(QColor(255, 255, 255, 55))
        border.setWidth(1)
        p.setPen(border)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(groove, 8, 8)

        ratio = (self.value() - self.minimum()) / max(1, (self.maximum() - self.minimum()))
        cx = int(round(groove.left() + ratio * (groove.width() - 1)))
        cy = groove.center().y()

        p.setPen(QPen(QColor(0, 0, 0, 220), 3))
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawEllipse(QPoint(cx, cy), 8, 8)

        p.end()

class _SoftSizeSlider(QSlider):
    def __init__(self, orientation: Qt.Orientation) -> None:
        super().__init__(orientation)
        self.setTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _groove_rect(self) -> QRect:
        return self.rect().adjusted(6, 8, -6, -8)

    def _set_value_from_pos(self, x: float) -> None:
        groove = self._groove_rect()
        if groove.width() <= 1:
            return

        pos = max(groove.left(), min(groove.right(), int(round(x))))
        ratio = (pos - groove.left()) / max(1.0, float(groove.width() - 1))
        value = self.minimum() + ratio * (self.maximum() - self.minimum())
        self.setValue(int(round(value)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._set_value_from_pos(event.position().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_value_from_pos(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        groove = self._groove_rect()

        track_pen = QPen(QColor(255, 255, 255, 22))
        track_pen.setWidth(1)
        p.setPen(track_pen)
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(QRectF(groove), 4, 4)

        ratio = (self.value() - self.minimum()) / max(1, (self.maximum() - self.minimum()))
        fill_w = int(round(ratio * groove.width()))
        fill_rect = QRect(groove.left(), groove.top(), max(8, fill_w), groove.height())

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 155))
        p.drawRoundedRect(QRectF(fill_rect), 4, 4)

        cx = int(round(groove.left() + ratio * (groove.width() - 1)))
        cy = groove.center().y()

        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawEllipse(QPointF(cx, cy), 7.5, 7.5)

        p.end()

class _Card(QFrame):
    def __init__(self, *, header: str, body: str) -> None:
        super().__init__()
        self.setObjectName("Card")

        l = QVBoxLayout(self)
        l.setContentsMargins(18, 18, 18, 18)
        l.setSpacing(10)

        h = QLabel(header)
        h.setObjectName("CardTitle")

        b = QLabel(body)
        b.setObjectName("Muted")
        b.setWordWrap(True)

        l.addWidget(h)
        l.addWidget(b)
        l.addStretch(1)


class _PillLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("PillLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(12, 6, 12, 6)
        self.setStyleSheet(f"""
            QLabel#PillLabel{{
                color: #FFFFFF;
                background: {PILL_BG};
                border: 1px solid {PILL_BORDER};
                border-radius: 10px;
                font-weight: 600;
            }}
        """)


class _PillButton(QToolButton):
    def __init__(self, text: str, *, icon: QIcon) -> None:
        super().__init__()
        self.setText(text)
        self.setIcon(icon)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("PillButton")
        self.setStyleSheet(f"""
            QToolButton#PillButton{{
                color: #FFFFFF;
                background: {PILL_BG};
                border: 1px solid {PILL_BORDER};
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 600;
            }}
            QToolButton#PillButton:checked{{
                background: rgba(255,255,255,18);
                border: 1px solid rgba(255,255,255,90);
            }}
        """)

def _collect_split_paths(split: str) -> list[Path]:
    split_dir = DATASET_DIR / split
    out: list[Path] = []

    if not split_dir.exists():
        return out

    out.extend(sorted(split_dir.glob("*.png")))

    for d in range(10):
        digit_dir = split_dir / str(d)
        if not digit_dir.exists():
            continue
        out.extend(sorted(digit_dir.glob("*.png")))

    return out


def _split_snapshot(split: str) -> tuple[tuple[str, float], ...]:
    items: list[tuple[str, float]] = []

    for p in _collect_split_paths(split):
        try:
            mt = p.stat().st_mtime
        except Exception:
            mt = 0.0

        items.append((str(p), mt))

    return tuple(items)


def _make_gallery_item(path: Path) -> QListWidgetItem:
    item = QListWidgetItem()
    item.setText(path.stem)
    item.setData(Qt.ItemDataRole.UserRole, str(path))
    item.setSizeHint(QSize(CREATE_TILE_W, CREATE_TILE_H))

    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    img = reader.read()
    if not img.isNull():
        pm = QPixmap.fromImage(img).scaled(
            CREATE_TILE_ICON,
            CREATE_TILE_ICON,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        item.setIcon(QIcon(pm))

    return item


def _setup_gallery_widget(gallery: QListWidget) -> None:
    gallery.setViewMode(QListWidget.ViewMode.IconMode)
    gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
    gallery.setMovement(QListWidget.Movement.Static)
    gallery.setUniformItemSizes(True)
    gallery.setSpacing(CREATE_TILE_SPACING)
    gallery.setIconSize(QSize(CREATE_TILE_ICON, CREATE_TILE_ICON))
    gallery.setWordWrap(True)
    gallery.setGridSize(QSize(CREATE_TILE_W, CREATE_TILE_H))
    gallery.setMouseTracking(True)

    gallery.setStyleSheet("""
        QListWidget {
            background: transparent;
            border: none;
            outline: none;
        }
        QListWidget::item {
            background: #070707;
            border: 1px solid rgba(255,255,255,36);
            border-radius: 14px;
            padding: 6px 6px 2px 6px;
            margin: 2px;
            color: rgba(255,255,255,230);
        }
        QListWidget::item:hover {
            border: 1px solid rgba(255,255,255,72);
            background: #0b0b0b;
        }
        QListWidget::item:selected {
            border: 1px solid rgba(255,255,255,120);
            background: rgba(255,255,255,18);
            color: rgba(255,255,255,255);
        }
    """)
def _extract_index_from_name(stem: str) -> Optional[int]:
    if "_" in stem:
        tail = stem.rsplit("_", 1)[-1]
    else:
        tail = stem

    if not tail.isdigit():
        return None

    try:
        return int(tail)
    except Exception:
        return None

def _parse_hex_rgba(text: str) -> QColor:
    text = text.strip().upper()

    if not text:
        return QColor()

    if not text.startswith("#"):
        text = f"#{text}"

    try:
        if len(text) == 7:
            r = int(text[1:3], 16)
            g = int(text[3:5], 16)
            b = int(text[5:7], 16)
            return QColor(r, g, b, 255)

        if len(text) == 9:
            r = int(text[1:3], 16)
            g = int(text[3:5], 16)
            b = int(text[5:7], 16)
            a = int(text[7:9], 16)
            return QColor(r, g, b, a)
    except Exception:
        return QColor()

    return QColor()


def _color_to_hex_rgba(color: QColor) -> str:
    r = color.red()
    g = color.green()
    b = color.blue()
    a = color.alpha()

    if a >= 255:
        return f"#{r:02X}{g:02X}{b:02X}"

    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"

def _load_icon(path: Path, size: int = 18) -> QIcon:
    if path.exists():
        pm = QPixmap(str(path))
        if not pm.isNull():
            return QIcon(pm)
    return _make_fallback_tool_icon(size)


def _make_fallback_tool_icon(size: int) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(QColor(255, 255, 255, 220))
    pen.setWidthF(max(1.4, size * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    pad = max(2, int(round(size * 0.18)))
    p.drawRoundedRect(
        pad,
        pad,
        size - pad * 2 - 1,
        size - pad * 2 - 1,
        max(3, int(round(size * 0.18))),
        max(3, int(round(size * 0.18))),
    )
    p.drawLine(size // 2, pad + 2, size // 2, size - pad - 3)
    p.drawLine(pad + 2, size // 2, size - pad - 3, size // 2)

    p.end()
    return QIcon(pm)

def _make_grid_icon(size: int) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(QColor(255, 255, 255, 235))
    pen.setWidthF(max(1.2, size * 0.10))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    pad = size * 0.18
    x0 = pad
    y0 = pad
    x1 = size - pad
    y1 = size - pad

    p.drawRoundedRect(
        int(x0),
        int(y0),
        int(x1 - x0),
        int(y1 - y0),
        int(size * 0.18),
        int(size * 0.18),
    )

    vx1 = x0 + (x1 - x0) / 3.0
    vx2 = x0 + 2.0 * (x1 - x0) / 3.0
    hy1 = y0 + (y1 - y0) / 3.0
    hy2 = y0 + 2.0 * (y1 - y0) / 3.0

    p.drawLine(int(vx1), int(y0), int(vx1), int(y1))
    p.drawLine(int(vx2), int(y0), int(vx2), int(y1))
    p.drawLine(int(x0), int(hy1), int(x1), int(hy1))
    p.drawLine(int(x0), int(hy2), int(x1), int(hy2))

    p.end()
    return QIcon(pm)

def _make_undo_icon(size: int) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(QColor(255, 255, 255, 235))
    pen.setWidthF(max(1.5, size * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    y = size * 0.50
    x0 = size * 0.78
    x1 = size * 0.28
    a = size * 0.14

    p.drawLine(int(x0), int(y), int(x1), int(y))
    p.drawLine(int(x1), int(y), int(x1 + a), int(y - a))
    p.drawLine(int(x1), int(y), int(x1 + a), int(y + a))

    p.end()
    return QIcon(pm)

def _make_redo_icon(size: int) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(QColor(255, 255, 255, 235))
    pen.setWidthF(max(1.5, size * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    y = size * 0.50
    x0 = size * 0.22
    x1 = size * 0.72
    a = size * 0.14

    p.drawLine(int(x0), int(y), int(x1), int(y))
    p.drawLine(int(x1), int(y), int(x1 - a), int(y - a))
    p.drawLine(int(x1), int(y), int(x1 - a), int(y + a))

    p.end()
    return QIcon(pm)