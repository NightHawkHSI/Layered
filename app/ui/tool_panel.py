"""Tool panel: pick active tool + brush settings (size, hardness, opacity)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..tools import Tool, ToolContext


class ToolPanel(QWidget):
    tool_selected = pyqtSignal(str)
    brush_size_changed = pyqtSignal(int)

    def __init__(self, ctx: ToolContext, tools: dict[str, Tool], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tools"))

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._grid_host)

        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for name in tools.keys():
            self._add_button(name)

        if tools:
            first = next(iter(tools))
            self._buttons[first].setChecked(True)

        # --- Brush settings group ---
        group = QGroupBox("Brush settings")
        g_layout = QVBoxLayout(group)

        # Size: spin box + slider, kept in sync
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Size"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 1024)
        self.size_spin.setValue(ctx.brush_size)
        self.size_spin.valueChanged.connect(self._on_size_change)
        size_row.addWidget(self.size_spin)
        g_layout.addLayout(size_row)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, 256)
        self.size_slider.setValue(min(ctx.brush_size, 256))
        self.size_slider.valueChanged.connect(self._on_size_slider)
        g_layout.addWidget(self.size_slider)

        # Hardness
        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("Hardness"))
        self.hardness_label = QLabel(f"{int(ctx.brush_hardness * 100)}%")
        h_row.addStretch(1)
        h_row.addWidget(self.hardness_label)
        g_layout.addLayout(h_row)
        self.hardness_slider = QSlider(Qt.Orientation.Horizontal)
        self.hardness_slider.setRange(0, 100)
        self.hardness_slider.setValue(int(ctx.brush_hardness * 100))
        self.hardness_slider.valueChanged.connect(self._on_hardness)
        g_layout.addWidget(self.hardness_slider)

        # Opacity
        o_row = QHBoxLayout()
        o_row.addWidget(QLabel("Opacity"))
        self.opacity_label = QLabel(f"{int(ctx.brush_opacity * 100)}%")
        o_row.addStretch(1)
        o_row.addWidget(self.opacity_label)
        g_layout.addLayout(o_row)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(int(ctx.brush_opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        g_layout.addWidget(self.opacity_slider)

        # Spacing
        sp_row = QHBoxLayout()
        sp_row.addWidget(QLabel("Spacing"))
        self.spacing_label = QLabel(f"{int(ctx.brush_spacing * 100)}%")
        sp_row.addStretch(1)
        sp_row.addWidget(self.spacing_label)
        g_layout.addLayout(sp_row)
        self.spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.spacing_slider.setRange(1, 100)
        self.spacing_slider.setValue(int(ctx.brush_spacing * 100))
        self.spacing_slider.valueChanged.connect(self._on_spacing)
        g_layout.addWidget(self.spacing_slider)

        layout.addWidget(group)
        layout.addStretch(1)

    # --- internals ---

    def _add_button(self, name: str) -> None:
        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
        self._group.addButton(btn)
        count = self._grid.count()
        self._grid.addWidget(btn, count // 2, count % 2)
        self._buttons[name] = btn

    def add_tool_button(self, name: str) -> None:
        if name in self._buttons:
            return
        self._add_button(name)

    # --- handlers ---

    def _on_size_change(self, v: int) -> None:
        self.ctx.brush_size = v
        if self.size_slider.value() != min(v, self.size_slider.maximum()):
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(min(v, self.size_slider.maximum()))
            self.size_slider.blockSignals(False)
        self.brush_size_changed.emit(v)

    def _on_size_slider(self, v: int) -> None:
        if self.size_spin.value() != v:
            self.size_spin.setValue(v)

    def _on_hardness(self, v: int) -> None:
        self.ctx.brush_hardness = v / 100.0
        self.hardness_label.setText(f"{v}%")

    def _on_opacity(self, v: int) -> None:
        self.ctx.brush_opacity = v / 100.0
        self.opacity_label.setText(f"{v}%")

    def _on_spacing(self, v: int) -> None:
        self.ctx.brush_spacing = v / 100.0
        self.spacing_label.setText(f"{v}%")
