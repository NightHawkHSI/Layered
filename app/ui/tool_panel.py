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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..tools import Tool, ToolContext
from .slider_field import SliderField


# Which brush-settings each tool actually uses. Tools missing from the map
# get no settings shown.
TOOL_SETTINGS: dict[str, list[str]] = {
    "🖌️ Brush":       ["size", "hardness", "opacity", "spacing"],
    "🧹 Eraser":      ["size", "hardness", "opacity", "spacing"],
    "😶‍🌫️ Blur":        ["size", "hardness", "opacity", "spacing"],
    "✨ Sharpen":     ["size", "hardness", "opacity", "spacing"],
    "👆 Smudge":      ["size", "hardness", "opacity", "spacing"],
    "📋 Clone Stamp": ["size", "hardness", "opacity", "spacing"],
    "📏 Line":        ["size", "opacity"],
    "🟦 Rectangle":   ["size", "opacity", "fill_shape"],
    "⭕ Ellipse":     ["size", "opacity", "fill_shape"],
    "🎨 Fill":        ["tolerance"],
    "🪄 Magic Wand":  ["tolerance"],
    "🌈 Gradient":    [],
    "📝 Text":        [],
    "🎯 Picker":      [],
    "✋ Move":        [],
    "🔲 Transform":   [],
    "⬜ Marquee":     [],
    "🔗 Lasso":       [],
    "🔧 Sel Transform": [],
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
        elif layout == "tools_dock":
            self._build_tools_grid(tools)
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

        self.hardness_slider = self._make_pct_row(
            g_layout, "Hardness", self.ctx.brush_hardness, 0, 100, self._on_hardness
        )
        self.opacity_slider = self._make_pct_row(
            g_layout, "Opacity", self.ctx.brush_opacity, 1, 100, self._on_opacity
        )
        self.spacing_slider = self._make_pct_row(
            g_layout, "Spacing", self.ctx.brush_spacing, 1, 100, self._on_spacing
        )

        layout.addWidget(group)
        layout.addStretch(1)

    # --- tools-only dock grid (no inline brush settings — settings go on a top toolbar) -----

    def _build_tools_grid(self, tools: dict[str, Tool]) -> None:
        self.setMinimumSize(0, 0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        outer.addWidget(self._grid_host)
        for name in tools.keys():
            self._add_button(name)
        if tools:
            self._buttons[next(iter(tools))].setChecked(True)
            self._active_tool_name = next(iter(tools))
        outer.addStretch(1)

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
        if self._layout_mode not in ("toolbar", "tools_dock"):
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
        self.hardness_slider = self._make_compact_pct_widgets(
            self.ctx.brush_hardness, 0, 100, self._on_hardness
        )
        hardness_actions.append(toolbar.addWidget(self.hardness_slider))
        hardness_actions.append(toolbar.addSeparator())
        self._setting_actions["hardness"] = hardness_actions

        # --- opacity ---
        opacity_actions: list[QAction] = []
        opacity_actions.append(toolbar.addWidget(QLabel("Opacity")))
        self.opacity_slider = self._make_compact_pct_widgets(
            self.ctx.brush_opacity, 1, 100, self._on_opacity
        )
        opacity_actions.append(toolbar.addWidget(self.opacity_slider))
        opacity_actions.append(toolbar.addSeparator())
        self._setting_actions["opacity"] = opacity_actions

        # --- spacing ---
        spacing_actions: list[QAction] = []
        spacing_actions.append(toolbar.addWidget(QLabel("Spacing")))
        self.spacing_slider = self._make_compact_pct_widgets(
            self.ctx.brush_spacing, 1, 100, self._on_spacing
        )
        spacing_actions.append(toolbar.addWidget(self.spacing_slider))
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
        self.tolerance_slider = self._make_compact_int_widgets(
            int(self.ctx.fill_tolerance), 0, 255, self._on_tolerance
        )
        tol_actions.append(toolbar.addWidget(self.tolerance_slider))
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
        if not self._setting_actions:
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

    def _make_compact_pct_widgets(self, init: float, lo: int, hi: int, slot) -> SliderField:
        sf = SliderField(lo, hi, int(init * 100), suffix="%", slider_width=90)
        sf.valueChanged.connect(slot)
        return sf

    def _make_compact_int_widgets(self, init: int, lo: int, hi: int, slot) -> SliderField:
        sf = SliderField(lo, hi, int(init), slider_width=90)
        sf.valueChanged.connect(slot)
        return sf

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
                      lo: int, hi: int, slot) -> SliderField:
        parent_layout.addWidget(QLabel(label))
        sf = SliderField(lo, hi, int(init * 100), suffix="%")
        sf.valueChanged.connect(slot)
        parent_layout.addWidget(sf)
        return sf

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # --- internals ----------------------------------------------------------

    def _add_button(self, name: str) -> None:
        if name == "\U0001f58c\ufe0f Brush":  # 🖌️ Brush — split button with preset picker
            btn = QToolButton()
            btn.setText(name)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
            self._group.addButton(btn)
            if self._layout_mode == "toolbar":
                btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                fm = btn.fontMetrics()
                btn.setMinimumWidth(fm.horizontalAdvance(name) + 32)
                btn.setMinimumHeight(26)
            else:
                count = self._grid.count()
                self._grid.addWidget(btn, count // 2, count % 2)
            self._buttons[name] = btn
            return

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

    def remove_tool_button(self, name: str) -> None:
        btn = self._buttons.pop(name, None)
        if btn is None:
            return
        self._group.removeButton(btn)
        btn.setParent(None)
        btn.deleteLater()

    def set_brush_presets(self, presets_by_category: dict) -> None:
        """Populate the Brush button's dropdown menu with category submenus.

        ``presets_by_category`` maps category name → list of
        ``BrushPreset`` objects (from ``app.brush_loader``).
        Hovering over a category in the menu opens its submenu; clicking
        a preset applies all of its parameters and activates the Brush
        tool.
        """
        from PyQt6.QtWidgets import QMenu
        btn = self._buttons.get("\U0001f58c\ufe0f Brush")  # 🖌️ Brush
        if btn is None or not isinstance(btn, QToolButton):
            return
        menu = QMenu(btn)
        for category, presets in presets_by_category.items():
            if not presets:
                continue
            sub = menu.addMenu(category)
            for preset in presets:
                label = f"{preset.icon}  {preset.name}  ({preset.size}px)"
                action = sub.addAction(label)
                action.triggered.connect(
                    lambda _=False, p=preset: self._apply_preset(p)
                )
        btn.setMenu(menu)

    def set_tool_categories(self, categories: dict[str, list[str]]) -> None:
        """Replace all individual tool buttons with one split-button per
        category folder.  Each split-button shows the currently active tool
        name; the popup menu lets the user switch to any other tool in that
        folder.  "Basic" is always placed first; remaining categories follow
        in their original discovery order.

        ``categories`` maps category name → ordered list of tool display names.
        """
        from PyQt6.QtWidgets import QMenu

        # Basic first, then the rest in stable order.
        ordered = sorted(categories.items(), key=lambda kv: (0 if kv[0] == "Basic" else 1, kv[0]))

        # Tear down every existing per-tool button.
        for btn in list(self._buttons.values()):
            self._group.removeButton(btn)
            self._grid.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._buttons.clear()

        first_btn: QToolButton | None = None
        for _cat, names in ordered:
            if not names:
                continue
            primary = names[0]

            split = QToolButton()
            split.setText(primary)
            split.setCheckable(True)
            split.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            split.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            if len(names) > 1:
                split.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                menu = QMenu(split)
                for name in names:
                    action = menu.addAction(name)
                    action.triggered.connect(
                        lambda _=False, n=name, s=split: self._on_category_pick(n, s)
                    )
                split.setMenu(menu)
            else:
                split.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)

            split.clicked.connect(
                lambda _=False, s=split: self.tool_selected.emit(s.text())
            )

            self._group.addButton(split)
            self._buttons[primary] = split
            count = self._grid.count()
            self._grid.addWidget(split, count // 2, count % 2)

            if first_btn is None:
                first_btn = split

        if first_btn is not None:
            first_btn.setChecked(True)
            self._active_tool_name = first_btn.text()

    def _on_category_pick(self, name: str, split_btn: "QToolButton") -> None:
        """Switch the split-button label to ``name`` and emit tool_selected."""
        # Remap _buttons so the new active tool name resolves to this button.
        old_key = next((k for k, v in self._buttons.items() if v is split_btn), None)
        if old_key and old_key != name:
            self._buttons.pop(old_key)
            self._buttons[name] = split_btn
        split_btn.setText(name)
        split_btn.setChecked(True)
        self._active_tool_name = name
        self.tool_selected.emit(name)

    def _apply_preset(self, preset) -> None:
        """Apply ``preset`` fields to the tool context and sync all sliders."""
        self.ctx.brush_size = preset.size
        self.ctx.brush_hardness = preset.hardness
        self.ctx.brush_opacity = preset.opacity
        self.ctx.brush_spacing = preset.spacing
        # Sync toolbar / panel slider widgets if they have been built yet.
        if hasattr(self, "size_spin"):
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(preset.size)
            self.size_spin.blockSignals(False)
        if hasattr(self, "size_slider"):
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(min(preset.size, self.size_slider.maximum()))
            self.size_slider.blockSignals(False)
        if hasattr(self, "hardness_slider"):
            self.hardness_slider.setValue(int(preset.hardness * 100))
        if hasattr(self, "opacity_slider"):
            self.opacity_slider.setValue(int(preset.opacity * 100))
        if hasattr(self, "spacing_slider"):
            self.spacing_slider.setValue(int(preset.spacing * 100))
        # Check the Brush button and emit tool_selected so canvas switches.
        btn = self._buttons.get("\U0001f58c\ufe0f Brush")  # 🖌️ Brush
        if btn is not None:
            btn.setChecked(True)
        self.tool_selected.emit("\U0001f58c\ufe0f Brush")  # 🖌️ Brush

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

    def _on_opacity(self, v: int) -> None:
        self.ctx.brush_opacity = v / 100.0

    def _on_spacing(self, v: int) -> None:
        self.ctx.brush_spacing = v / 100.0

    def _on_fill_shape(self, on: bool) -> None:
        self.ctx.fill_shape = bool(on)

    def _on_tolerance(self, v: int) -> None:
        self.ctx.fill_tolerance = int(v)
        cb = getattr(self.ctx, "on_tolerance_changed", None)
        if cb is not None:
            cb()
