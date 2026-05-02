"""Layer panel: list, add/remove, opacity, blend mode, visibility, reorder."""
from __future__ import annotations

from typing import Optional

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..blending import BLEND_MODES
from ..layer import LayerStack


def _layer_thumbnail(image, size: int) -> QPixmap:
    """Build a QPixmap thumbnail from a Pillow image, max edge = size."""
    if image is None:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        return pm
    w, h = image.size
    if w == 0 or h == 0:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        return pm
    scale = min(size / w, size / h)
    tw, th = max(1, int(w * scale)), max(1, int(h * scale))
    thumb = image.resize((tw, th))
    qimg = QImage(ImageQt(thumb).copy())
    return QPixmap.fromImage(qimg)


class LayerPanel(QWidget):
    changed = pyqtSignal()
    committed = pyqtSignal(str)  # discrete user actions worth a history entry
    duplicate_requested = pyqtSignal()
    export_requested = pyqtSignal()

    def __init__(self, stack: LayerStack, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.stack = stack

        self.list = QListWidget()
        self.list.setIconSize(QSize(40, 40))
        self.list.setMinimumHeight(60)
        self.list.setMinimumWidth(0)
        self.list.setUniformItemSizes(True)
        self.setMinimumSize(0, 0)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemChanged.connect(self._on_item_changed)

        # Compact glyphs + tooltips so the button row can shrink to a
        # narrow dock width on small screens. Letting Qt size each
        # button by its label text was forcing the panel's minimum
        # width to ~6×label width, which kept the dock too wide on
        # smaller / scaled displays.
        self.add_btn = QPushButton("＋")
        self.add_btn.setToolTip("Add layer")
        self.dup_btn = QPushButton("⎘")
        self.dup_btn.setToolTip("Duplicate the selected layer (Ctrl+J)")
        self.del_btn = QPushButton("✕")
        self.del_btn.setToolTip("Delete the selected layer (Del)")
        self.up_btn = QPushButton("▲")
        self.up_btn.setToolTip("Move layer up")
        self.down_btn = QPushButton("▼")
        self.down_btn.setToolTip("Move layer down")
        self.rename_btn = QPushButton("✎")
        self.rename_btn.setToolTip("Rename layer")
        self.add_btn.clicked.connect(self._on_add)
        self.dup_btn.clicked.connect(self.duplicate_requested.emit)
        self.del_btn.clicked.connect(self._on_del)
        self.up_btn.clicked.connect(self._on_up)
        self.down_btn.clicked.connect(self._on_down)
        self.rename_btn.clicked.connect(self._on_rename)

        self._del_shortcut = QShortcut(QKeySequence("Delete"), self.list)
        self._del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._del_shortcut.activated.connect(self._on_del)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        btn_row.setContentsMargins(0, 0, 0, 0)
        for b in (self.add_btn, self.dup_btn, self.del_btn, self.up_btn, self.down_btn, self.rename_btn):
            b.setMinimumWidth(0)
            b.setMaximumWidth(48)
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            btn_row.addWidget(b, 1)

        self.blend_combo = QComboBox()
        self.blend_combo.addItems(list(BLEND_MODES.keys()))
        self.blend_combo.currentTextChanged.connect(self._on_blend_change)
        self.blend_combo.setMinimumWidth(0)
        self.blend_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_change)
        self.opacity_slider.sliderReleased.connect(self._on_opacity_release)
        self.opacity_slider.setMinimumWidth(0)
        self.opacity_slider.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Layers"))
        layout.addWidget(self.list, 1)
        layout.addLayout(btn_row)
        layout.addWidget(QLabel("Blend mode"))
        layout.addWidget(self.blend_combo)
        layout.addWidget(QLabel("Opacity"))
        layout.addWidget(self.opacity_slider)

        self.export_btn = QPushButton("Export…")
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.export_btn.setMinimumWidth(0)
        self.export_btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.export_btn)

        self.refresh()

    # --- view sync ---

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for layer in reversed(self.stack.layers):  # show topmost first
            item = QListWidgetItem(layer.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
            item.setIcon(QIcon(_layer_thumbnail(layer.image, 40)))
            self.list.addItem(item)

        if self.stack.active_index >= 0:
            ui_row = len(self.stack.layers) - 1 - self.stack.active_index
            self.list.setCurrentRow(ui_row)
            active = self.stack.active
            if active is not None:
                self.blend_combo.blockSignals(True)
                self.blend_combo.setCurrentText(active.blend_mode)
                self.blend_combo.blockSignals(False)
                self.opacity_slider.blockSignals(True)
                self.opacity_slider.setValue(int(active.opacity * 100))
                self.opacity_slider.blockSignals(False)
        self.list.blockSignals(False)

    def _ui_row_to_index(self, row: int) -> int:
        return len(self.stack.layers) - 1 - row

    # --- handlers ---

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.set_active(self._ui_row_to_index(row))
        self.refresh()
        self.changed.emit()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        row = self.list.row(item)
        idx = self._ui_row_to_index(row)
        if 0 <= idx < len(self.stack.layers):
            layer = self.stack.layers[idx]
            old_visible = layer.visible
            old_name = layer.name
            layer.visible = item.checkState() == Qt.CheckState.Checked
            new_name = item.text().strip()
            if new_name:
                layer.name = new_name
            self.stack.invalidate_cache()
            self.changed.emit()
            if layer.visible != old_visible:
                self.committed.emit(f"{'Show' if layer.visible else 'Hide'} {layer.name}")
            elif layer.name != old_name:
                self.committed.emit(f"Rename to {layer.name}")

    def _on_add(self) -> None:
        self.stack.add_layer()
        self.refresh()
        self.changed.emit()
        self.committed.emit("Add layer")

    def _on_del(self) -> None:
        if self.stack.active is None:
            return
        name = self.stack.active.name
        self.stack.remove_active()
        self.refresh()
        self.changed.emit()
        self.committed.emit(f"Delete {name}")

    def _on_up(self) -> None:
        if self.stack.active_index < 0:
            return
        self.stack.move(self.stack.active_index, self.stack.active_index + 1)
        self.refresh()
        self.changed.emit()
        self.committed.emit("Move layer up")

    def _on_down(self) -> None:
        if self.stack.active_index < 0:
            return
        self.stack.move(self.stack.active_index, self.stack.active_index - 1)
        self.refresh()
        self.changed.emit()
        self.committed.emit("Move layer down")

    def _on_rename(self) -> None:
        layer = self.stack.active
        if layer is None:
            return
        text, ok = QInputDialog.getText(self, "Rename layer", "Name:", text=layer.name)
        if ok and text.strip():
            layer.name = text.strip()
            self.refresh()
            self.changed.emit()
            self.committed.emit(f"Rename to {layer.name}")

    def _on_blend_change(self, mode: str) -> None:
        layer = self.stack.active
        if layer is None:
            return
        layer.blend_mode = mode
        self.stack.invalidate_cache()
        self.changed.emit()
        self.committed.emit(f"Blend → {mode}")

    def _on_opacity_change(self, value: int) -> None:
        layer = self.stack.active
        if layer is None:
            return
        layer.opacity = value / 100.0
        self.stack.invalidate_cache()
        self.changed.emit()

    def _on_opacity_release(self) -> None:
        layer = self.stack.active
        if layer is None:
            return
        self.committed.emit(f"Opacity {int(layer.opacity * 100)}%")
