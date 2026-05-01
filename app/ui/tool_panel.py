"""Tool panel: pick active tool + brush settings (size, hardness, opacity).

Two layouts supported:
  * "panel"   — vertical, suited for a side dock.
  * "toolbar" — horizontal, suited for a top hot bar.

In toolbar mode, the host wires two `QToolBar`s — `populate_toolbar` fills
the first row with tool buttons; `populate_settings_toolbar` fills the
second row with the brush settings. `set_active_tool` then shows only the
settings relevant to that tool, hiding the rest to cut visual noise.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
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


# Which brush-settings each tool actually uses. Tools missing from the map
# get no settings shown.
TOOL_SETTINGS: dict[str, list[str]] = {
    "Brush":       ["size", "hardness", "opacity", "spacing"],
    "Eraser":      ["size", "hardness", "opacity", "spacing"],
    "Blur":        ["size", "hardness", "opacity", "spacing"],
    "Sharpen":     ["size", "hardness", "opacity", "spacing"],
    "Smudge":      ["size", "hardness", "opacity", "spacing"],
    "Clone Stamp": ["size", "hardness", "opacity", "spacing"],
    "Line":        ["size", "opacity"],
    "Rectangle":   ["size", "opacity", "fill_shape"],
    "Ellipse":     ["size", "opacity", "fill_shape"],
    "Fill":        ["tolerance"],
    "Magic Wand":  ["tolerance"],
    "Gradient":    [],
    "Text":        [],
    "Picker":      [],
    "Move":        [],
    "Transform":   [],
    "Marquee":     [],
    "Lasso":       [],
}


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
        # Toolbar-mode bookkeeping: per-setting list of QActions to toggle.
        self._setting_actions: dict[str, list[QAction]] = {}
        self._active_tool_name: Optional[str] = None

        if layout == "toolbar":
            self._build_toolbar(tools)
        else:
            self._build_panel(tools)

    # --- panel layout -------------------------------------------------------

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

    # --- toolbar layout -----------------------------------------------------

    def _build_toolbar(self, tools: dict[str, Tool]) -> None:
        # In toolbar mode, ToolPanel itself stays empty; controls are added
        # directly to QToolBars by `populate_toolbar` / `populate_settings_toolbar`.
        self._tools_for_toolbar = tools

    def populate_toolbar(self, toolbar) -> None:
        """Row 1: tool buttons only."""
        if self._layout_mode != "toolbar":
            return
        for name in self._tools_for_toolbar.keys():
            self._add_button(name)
            toolbar.addWidget(self._buttons[name])
        if self._tools_for_toolbar:
            first = next(iter(self._tools_for_toolbar))
            self._buttons[first].setChecked(True)
            self._active_tool_name = first

    def populate_settings_toolbar(self, toolbar) -> None:
        """Row 2: brush settings, shown/hidden per active tool."""
        if self._layout_mode != "toolbar":
            return
        from PyQt6.QtWidgets import QCheckBox

        # --- size ---
        size_actions: list[QAction] = []
        size_actions.append(toolbar.addWidget(QLabel("Size")))
        self.size_spin = self._make_size_spin()
        size_actions.append(toolbar.addWidget(self.size_spin))
        self.size_slider = self._make_size_slider()
        self.size_slider.setFixedWidth(120)
        size_actions.append(toolbar.addWidget(self.size_slider))
        size_actions.append(toolbar.addSeparator())
        self._setting_actions["size"] = size_actions

        # --- hardness ---
        hardness_actions: list[QAction] = []
        hardness_actions.append(toolbar.addWidget(QLabel("Hardness")))
        self.hardness_slider, self.hardness_label = self._make_compact_pct_widgets(
            self.ctx.brush_hardness, 0, 100, self._on_hardness
        )
        hardness_actions.append(toolbar.addWidget(self.hardness_slider))
        hardness_actions.append(toolbar.addWidget(self.hardness_label))
        hardness_actions.append(toolbar.addSeparator())
        self._setting_actions["hardness"] = hardness_actions

        # --- opacity ---
        opacity_actions: list[QAction] = []
        opacity_actions.append(toolbar.addWidget(QLabel("Opacity")))
        self.opacity_slider, self.opacity_label = self._make_compact_pct_widgets(
            self.ctx.brush_opacity, 1, 100, self._on_opacity
        )
        opacity_actions.append(toolbar.addWidget(self.opacity_slider))
        opacity_actions.append(toolbar.addWidget(self.opacity_label))
        opacity_actions.append(toolbar.addSeparator())
        self._setting_actions["opacity"] = opacity_actions

        # --- spacing ---
        spacing_actions: list[QAction] = []
        spacing_actions.append(toolbar.addWidget(QLabel("Spacing")))
        self.spacing_slider, self.spacing_label = self._make_compact_pct_widgets(
            self.ctx.brush_spacing, 1, 100, self._on_spacing
        )
        spacing_actions.append(toolbar.addWidget(self.spacing_slider))
        spacing_actions.append(toolbar.addWidget(self.spacing_label))
        spacing_actions.append(toolbar.addSeparator())
        self._setting_actions["spacing"] = spacing_actions

        # --- fill_shape ---
        fill_actions: list[QAction] = []
        self.fill_shape_box = QCheckBox("Fill shape")
        self.fill_shape_box.setChecked(self.ctx.fill_shape)
        self.fill_shape_box.toggled.connect(self._on_fill_shape)
        fill_actions.append(toolbar.addWidget(self.fill_shape_box))
        fill_actions.append(toolbar.addSeparator())
        self._setting_actions["fill_shape"] = fill_actions

        # --- tolerance ---
        tol_actions: list[QAction] = []
        tol_actions.append(toolbar.addWidget(QLabel("Tolerance")))
        self.tolerance_slider, self.tolerance_label = self._make_compact_int_widgets(
            int(self.ctx.fill_tolerance), 0, 255, self._on_tolerance
        )
        tol_actions.append(toolbar.addWidget(self.tolerance_slider))
        tol_actions.append(toolbar.addWidget(self.tolerance_label))
        tol_actions.append(toolbar.addSeparator())
        self._setting_actions["tolerance"] = tol_actions

        # Apply current tool's filter on first paint.
        if self._active_tool_name:
            self.set_active_tool(self._active_tool_name)

    def set_active_tool(self, name: str) -> None:
        """Grey out settings not used by `name`. Layout stays fixed in size
        so swapping tools doesn't reflow the toolbar — unused settings are
        kept visible but disabled, signalling they exist for other tools."""
        self._active_tool_name = name
        if self._layout_mode != "toolbar" or not self._setting_actions:
            return
        wanted = set(TOOL_SETTINGS.get(name, []))
        for key, actions in self._setting_actions.items():
            enabled = key in wanted
            for a in actions:
                w = a.defaultWidget() if hasattr(a, "defaultWidget") else None
                if w is not None:
                    w.setEnabled(enabled)
                else:
                    a.setEnabled(enabled)

    def _make_compact_pct_widgets(self, init: float, lo: int, hi: int, slot):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(init * 100))
        s.setFixedWidth(90)
        s.valueChanged.connect(slot)
        lab = QLabel(f"{int(init * 100)}%")
        lab.setMinimumWidth(38)
        return s, lab

    def _make_compact_int_widgets(self, init: int, lo: int, hi: int, slot):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(init))
        s.setFixedWidth(90)
        s.valueChanged.connect(slot)
        lab = QLabel(str(int(init)))
        lab.setMinimumWidth(38)
        return s, lab

    # --- widget builders ----------------------------------------------------

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

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # --- internals ----------------------------------------------------------

    def _add_button(self, name: str) -> None:
        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
        self._group.addButton(btn)
        if self._layout_mode == "toolbar":
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            fm = btn.fontMetrics()
            btn.setMinimumWidth(fm.horizontalAdvance(name) + 18)
            btn.setMinimumHeight(26)
        else:
            count = self._grid.count()
            self._grid.addWidget(btn, count // 2, count % 2)
        self._buttons[name] = btn

    def add_tool_button(self, name: str, toolbar=None) -> None:
        if name in self._buttons:
            return
        self._add_button(name)
        if toolbar is not None and self._layout_mode == "toolbar":
            toolbar.addWidget(self._buttons[name])

    # --- handlers -----------------------------------------------------------

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

    def _on_fill_shape(self, on: bool) -> None:
        self.ctx.fill_shape = bool(on)

    def _on_tolerance(self, v: int) -> None:
        self.ctx.fill_tolerance = int(v)
        if getattr(self, "tolerance_label", None) is not None:
            self.tolerance_label.setText(str(int(v)))
