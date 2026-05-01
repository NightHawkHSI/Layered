"""Tool panel: pick active tool + brush settings (size, hardness, opacity).

Two layouts supported:
  * "panel"   — vertical, suited for a side dock.
  * "toolbar" — horizontal, suited for a top hot bar.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..tools import Tool, ToolContext


class ToolPanel(QWidget):
    tool_selected = pyqtSignal(str)
    brush_size_changed = pyqtSignal(int)

    def __init__(self, ctx: ToolContext, tools: dict[str, Tool], parent: Optional[QWidget] = None,
                 layout: str = "panel"):
        super().__init__(parent)
        self.ctx = ctx
        self._layout_mode = layout
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        if layout == "toolbar":
            self._build_toolbar(tools)
        else:
            self._build_panel(tools)

    # --- layouts ---

    def _build_panel(self, tools: dict[str, Tool]) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tools"))

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._grid_host)

        for name in tools.keys():
            self._add_button(name)
        if tools:
            self._buttons[next(iter(tools))].setChecked(True)

        group = QGroupBox("Brush settings")
        g_layout = QVBoxLayout(group)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Size"))
        self.size_spin = self._make_size_spin()
        size_row.addWidget(self.size_spin)
        g_layout.addLayout(size_row)

        self.size_slider = self._make_size_slider()
        g_layout.addWidget(self.size_slider)

        self.hardness_slider, self.hardness_label = self._make_pct_row(
            g_layout, "Hardness", self.ctx.brush_hardness, 0, 100, self._on_hardness
        )
        self.opacity_slider, self.opacity_label = self._make_pct_row(
            g_layout, "Opacity", self.ctx.brush_opacity, 1, 100, self._on_opacity
        )
        self.spacing_slider, self.spacing_label = self._make_pct_row(
            g_layout, "Spacing", self.ctx.brush_spacing, 1, 100, self._on_spacing
        )

        layout.addWidget(group)
        layout.addStretch(1)

    def _build_toolbar(self, tools: dict[str, Tool]) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)

        self._tool_row_host = QWidget()
        self._tool_row = QHBoxLayout(self._tool_row_host)
        self._tool_row.setContentsMargins(0, 0, 0, 0)
        self._tool_row.setSpacing(2)
        for name in tools.keys():
            self._add_button(name)
        if tools:
            self._buttons[next(iter(tools))].setChecked(True)
        row.addWidget(self._tool_row_host)

        row.addWidget(self._sep())

        row.addWidget(QLabel("Size"))
        self.size_spin = self._make_size_spin()
        row.addWidget(self.size_spin)
        self.size_slider = self._make_size_slider()
        self.size_slider.setFixedWidth(120)
        row.addWidget(self.size_slider)

        self.hardness_slider, self.hardness_label = self._make_compact_pct(
            row, "Hardness", self.ctx.brush_hardness, 0, 100, self._on_hardness
        )
        self.opacity_slider, self.opacity_label = self._make_compact_pct(
            row, "Opacity", self.ctx.brush_opacity, 1, 100, self._on_opacity
        )
        self.spacing_slider, self.spacing_label = self._make_compact_pct(
            row, "Spacing", self.ctx.brush_spacing, 1, 100, self._on_spacing
        )

        row.addStretch(1)

    # --- widget builders ---

    def _make_size_spin(self) -> QSpinBox:
        w = QSpinBox()
        w.setRange(1, 1024)
        w.setValue(self.ctx.brush_size)
        w.valueChanged.connect(self._on_size_change)
        return w

    def _make_size_slider(self) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(1, 256)
        s.setValue(min(self.ctx.brush_size, 256))
        s.valueChanged.connect(self._on_size_slider)
        return s

    def _make_pct_row(self, parent_layout: QVBoxLayout, label: str, init: float,
                      lo: int, hi: int, slot) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        lab = QLabel(f"{int(init * 100)}%")
        row.addStretch(1)
        row.addWidget(lab)
        parent_layout.addLayout(row)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(init * 100))
        s.valueChanged.connect(slot)
        parent_layout.addWidget(s)
        return s, lab

    def _make_compact_pct(self, row: QHBoxLayout, label: str, init: float,
                          lo: int, hi: int, slot) -> tuple[QSlider, QLabel]:
        row.addWidget(self._sep())
        row.addWidget(QLabel(label))
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(init * 100))
        s.setFixedWidth(90)
        s.valueChanged.connect(slot)
        lab = QLabel(f"{int(init * 100)}%")
        lab.setMinimumWidth(38)
        row.addWidget(s)
        row.addWidget(lab)
        return s, lab

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # --- internals ---

    def _add_button(self, name: str) -> None:
        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
        self._group.addButton(btn)
        if self._layout_mode == "toolbar":
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._tool_row.addWidget(btn)
        else:
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
        if self.hardness_label is not None:
            self.hardness_label.setText(f"{v}%")

    def _on_opacity(self, v: int) -> None:
        self.ctx.brush_opacity = v / 100.0
        if self.opacity_label is not None:
            self.opacity_label.setText(f"{v}%")

    def _on_spacing(self, v: int) -> None:
        self.ctx.brush_spacing = v / 100.0
        if self.spacing_label is not None:
            self.spacing_label.setText(f"{v}%")
