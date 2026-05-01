"""Layer panel: list, add/remove, opacity, blend mode, visibility, reorder."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..blending import BLEND_MODES
from ..layer import LayerStack


class LayerPanel(QWidget):
    changed = pyqtSignal()
    committed = pyqtSignal(str)  # discrete user actions worth a history entry
    export_requested = pyqtSignal()

    def __init__(self, stack: LayerStack, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.stack = stack

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemChanged.connect(self._on_item_changed)

        self.add_btn = QPushButton("+ Add")
        self.del_btn = QPushButton("Delete")
        self.del_btn.setToolTip("Delete the selected layer (Del)")
        self.up_btn = QPushButton("Up")
        self.down_btn = QPushButton("Down")
        self.rename_btn = QPushButton("Rename")
        self.add_btn.clicked.connect(self._on_add)
        self.del_btn.clicked.connect(self._on_del)
        self.up_btn.clicked.connect(self._on_up)
        self.down_btn.clicked.connect(self._on_down)
        self.rename_btn.clicked.connect(self._on_rename)

        self._del_shortcut = QShortcut(QKeySequence("Delete"), self.list)
        self._del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._del_shortcut.activated.connect(self._on_del)

        btn_row = QHBoxLayout()
        for b in (self.add_btn, self.del_btn, self.up_btn, self.down_btn, self.rename_btn):
            btn_row.addWidget(b)

        self.blend_combo = QComboBox()
        self.blend_combo.addItems(list(BLEND_MODES.keys()))
        self.blend_combo.currentTextChanged.connect(self._on_blend_change)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_change)
        self.opacity_slider.sliderReleased.connect(self._on_opacity_release)

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
