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
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
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
# Icon glyph per tool — prefix text so the eye scans the row by shape, not
# letter. Falls back to "" (no icon) when the tool is not listed.
TOOL_ICONS: dict[str, str] = {
    "Brush":         "🖌",
    "Eraser":        "🩹",
    "Blur":          "💧",
    "Sharpen":       "🔪",
    "Smudge":        "👆",
    "Clone Stamp":   "🖇",
    "Line":          "╱",
    "Rectangle":     "▭",
    "Ellipse":       "◯",
    "Fill":          "🪣",
    "Magic Wand":    "✨",
    "Gradient":      "🌈",
    "Text":          "🅰",
    "Picker":        "💉",
    "Move":          "✥",
    "Transform":     "⛶",
    "Marquee":       "⬚",
    "Lasso":         "🪢",
    "Sel Transform": "◫",
    "Triangle":      "△",
    "Star":          "★",
    "Pentagon":      "⬠",
    "Hexagon":       "⬡",
    "Diamond":       "◇",
    "Arrow":         "➤",
    "Curve":         "∿",
    "Dashed":        "┈",

}

# Photoshop-ish single-key shortcuts. ApplicationShortcut scope so the key
# fires regardless of which dock has focus. Tools missing from the map get
# no shortcut.
TOOL_SHORTCUTS: dict[str, str] = {
    "Brush":         "B",
    "Eraser":        "E",
    "Fill":          "G",
    "Gradient":      "Shift+G",
    "Picker":        "I",
    "Move":          "V",
    "Marquee":       "M",
    "Lasso":         "L",
    "Magic Wand":    "W",
    "Text":          "T",
    "Transform":     "Ctrl+T",
    "Sel Transform": "Ctrl+Shift+T",
    "Line":          "U",
    "Rectangle":     "Shift+U",
    "Ellipse":       "Alt+U",
    "Blur":          "R",
    "Sharpen":       "Shift+R",
    "Smudge":        "Alt+R",
    "Clone Stamp":   "S",
}

# Stylesheet for tool buttons. Bumps checked-state contrast so the active
# tool reads at a glance and gives a hover hint for affordance.
_TOOL_BTN_QSS = """
QPushButton, QToolButton {
    text-align: left;
    padding: 4px 8px;
}
QPushButton:hover, QToolButton:hover {
    background: rgba(255,255,255,0.08);
}
QPushButton:checked, QToolButton:checked {
    background: #2a6ad6;
    color: white;
    border: 1px solid #4a8af0;
    font-weight: bold;
}
"""


def _default_icon_for(name: str) -> str:
    """Built-in fallback glyph. Custom brushes override this via set_tool_icon."""
    return TOOL_ICONS.get(name, "")


TOOL_SETTINGS: dict[str, list[str]] = {
    "Brush":           ["size", "hardness", "opacity", "spacing"],
    "Eraser":          ["size", "hardness", "opacity", "spacing"],
    "Blur":            ["size", "hardness", "opacity", "spacing"],
    "Sharpen":         ["size", "hardness", "opacity", "spacing"],
    "Smudge":          ["size", "hardness", "opacity", "spacing"],
    "Clone Stamp":     ["size", "hardness", "opacity", "spacing"],
    "Line":            ["size", "opacity"],
    "Rectangle":       ["size", "opacity", "fill_shape"],
    "Ellipse":         ["size", "opacity", "fill_shape"],
    "Fill":            ["tolerance"],
    "Magic Wand":      ["tolerance"],
    "Gradient":        [],
    "Text":            [],
    "Picker":          [],
    "Move":            [],
    "Transform":       [],
    "Marquee":         [],
    "Lasso":           [],
    "Sel Transform":   [],
}


class ToolPanel(QWidget):
    tool_selected = pyqtSignal(str)
    brush_size_changed = pyqtSignal(int)
    tool_order_changed = pyqtSignal(list)

    def __init__(self, ctx: ToolContext, tools: dict[str, Tool], parent: Optional[QWidget] = None,
                 layout: str = "panel"):
        super().__init__(parent)
        self.ctx = ctx
        self._layout_mode = layout
        self._buttons: dict[str, QPushButton] = {}
        self._shortcuts: dict[str, QShortcut] = {}
        # tool_id -> display name. Lets the panel resolve special tools
        # (e.g. the brush split-button) without hard-coding labels.
        self._id_to_name: dict[str, str] = {
            getattr(t, "tool_id", ""): n
            for n, t in tools.items()
            if getattr(t, "tool_id", "")
        }
        # Per-tool icon overrides (set by host before adding the button — lets
        # custom brushes ship their own glyph instead of inheriting TOOL_ICONS).
        self._icon_overrides: dict[str, str] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        # Toolbar-mode bookkeeping: per-setting list of QActions to toggle.
        self._setting_actions: dict[str, list[QAction]] = {}
        self._active_tool_name: Optional[str] = None
        self.setStyleSheet(_TOOL_BTN_QSS)

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
        self._grid.setSpacing(3)
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
        btn = self._buttons.get(name)
        if btn is None:
            for b in self._buttons.values():
                if b.property("tool_name") == name:
                    btn = b
                    break
        if btn is not None and not btn.isChecked():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
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

    def register_tool_id(self, tool_id: str, name: str) -> None:
        """Register a tool_id -> display-name mapping. Lets the panel resolve
        special tools (brush, etc.) without hard-coding their labels."""
        if tool_id and name:
            self._id_to_name[tool_id] = name

    def _name_for_id(self, tool_id: str) -> Optional[str]:
        return self._id_to_name.get(tool_id)

    def _add_button(self, name: str) -> None:
        label = self._label_for(name)
        tip = self._tooltip_for(name)
        if name == self._name_for_id("brush"):  # split button with preset picker
            btn = QToolButton()
            btn.setText(label)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
            self._group.addButton(btn)
            if self._layout_mode == "toolbar":
                btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                fm = btn.fontMetrics()
                btn.setMinimumWidth(fm.horizontalAdvance(label) + 32)
                btn.setMinimumHeight(28)
            else:
                btn.setMinimumHeight(30)
                count = self._grid.count()
                self._grid.addWidget(btn, count // 2, count % 2)
            self._buttons[name] = btn
            self._install_shortcut(name, btn)
            return

        btn = QPushButton(label)
        btn.setToolTip(tip)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, n=name: self.tool_selected.emit(n))
        self._group.addButton(btn)
        if self._layout_mode == "toolbar":
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            fm = btn.fontMetrics()
            btn.setMinimumWidth(fm.horizontalAdvance(label) + 18)
            btn.setMinimumHeight(28)
        else:
            btn.setMinimumHeight(30)
            count = self._grid.count()
            self._grid.addWidget(btn, count // 2, count % 2)
        self._buttons[name] = btn
        self._install_shortcut(name, btn)

    def _label_for(self, name: str) -> str:
        icon = self._icon_overrides.get(name) or _default_icon_for(name)
        return f"{icon}  {name}" if icon else name

    def _tooltip_for(self, name: str) -> str:
        sc = TOOL_SHORTCUTS.get(name)
        return f"{name}  ({sc})" if sc else name

    def set_tool_icon(self, name: str, icon: str) -> None:
        """Register a custom glyph for ``name``. Call before ``add_tool_button``
        / ``set_tool_categories`` for the icon to appear; if the button already
        exists, its label and tooltip are refreshed in place."""
        if not icon:
            return
        self._icon_overrides[name] = icon
        btn = self._buttons.get(name)
        if btn is not None:
            btn.setText(self._label_for(name))
            btn.setToolTip(self._tooltip_for(name))

    def _install_shortcut(self, name: str, btn) -> None:
        seq = TOOL_SHORTCUTS.get(name)
        if not seq or name in self._shortcuts:
            return
        sc = QShortcut(QKeySequence(seq), self)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(lambda b=btn, n=name: self._fire_shortcut(b, n))
        self._shortcuts[name] = sc

    def _fire_shortcut(self, btn, name: str) -> None:
        # Don't hijack single-letter keys while user is typing in a text
        # field, spin box, or any editable widget.
        from PyQt6.QtWidgets import (
            QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox,
        )
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return
        if isinstance(fw, QComboBox) and fw.isEditable():
            return
        btn.setChecked(True)
        self.tool_selected.emit(name)

    def add_tool_button(self, name: str, toolbar=None) -> None:
        if name in self._buttons:
            return
        self._add_button(name)
        if toolbar is not None and self._layout_mode == "toolbar":
            toolbar.addWidget(self._buttons[name])

    # --- reorder support ---------------------------------------------------

    def get_tool_order(self) -> list[str]:
        return list(self._buttons.keys())

    def set_tool_order(self, order: list[str]) -> None:
        """Reflow buttons in `order`. Names not in `order` keep relative order
        and are appended at the end. No-op if no buttons exist yet."""
        if not self._buttons:
            return
        new_buttons: dict = {}
        for n in order:
            if n in self._buttons:
                new_buttons[n] = self._buttons[n]
        for n, b in self._buttons.items():
            if n not in new_buttons:
                new_buttons[n] = b
        self._buttons = new_buttons
        if self._layout_mode in ("tools_dock", "panel"):
            grid = getattr(self, "_grid", None)
            if grid is None:
                return
            for btn in self._buttons.values():
                grid.removeWidget(btn)
            for i, btn in enumerate(self._buttons.values()):
                grid.addWidget(btn, i // 2, i % 2)

    def open_reorder_dialog(self) -> None:
        from PyQt6.QtWidgets import (
            QAbstractItemView,
            QDialog,
            QDialogButtonBox,
            QListWidget,
            QListWidgetItem,
            QVBoxLayout,
        )
        if not self._buttons:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Customize tool order")
        dlg.resize(280, 380)
        lay = QVBoxLayout(dlg)
        lst = QListWidget(dlg)
        lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        lst.setDefaultDropAction(Qt.DropAction.MoveAction)
        lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for n in self._buttons.keys():
            item = QListWidgetItem(self._label_for(n))
            item.setData(Qt.ItemDataRole.UserRole, n)
            lst.addItem(item)
        lay.addWidget(lst)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            order = [
                lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())
            ]
            self.set_tool_order(order)
            self.tool_order_changed.emit(order)

    def contextMenuEvent(self, e):  # noqa: N802
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Customize tool order...", self.open_reorder_dialog)
        m.exec(e.globalPos())

    def remove_tool_button(self, name: str) -> None:
        btn = self._buttons.pop(name, None)
        if btn is None:
            return
        self._group.removeButton(btn)
        btn.setParent(None)
        btn.deleteLater()
        sc = self._shortcuts.pop(name, None)
        if sc is not None:
            sc.setParent(None)
            sc.deleteLater()

    def set_brush_presets(self, presets_by_category: dict) -> None:
        """Populate the Brush button's dropdown menu with category submenus.

        ``presets_by_category`` maps category name → list of
        ``BrushPreset`` objects (from ``app.brush_loader``).
        Hovering over a category in the menu opens its submenu; clicking
        a preset applies all of its parameters and activates the Brush
        tool.
        """
        from PyQt6.QtWidgets import QMenu
        brush_name = self._name_for_id("brush")
        btn = self._buttons.get(brush_name) if brush_name else None
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
        for sc in self._shortcuts.values():
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts.clear()

        first_btn: QToolButton | None = None
        first_name: Optional[str] = None
        for _cat, names in ordered:
            if not names:
                continue
            primary = names[0]

            split = QToolButton()
            split.setText(self._label_for(primary))
            split.setToolTip(self._tooltip_for(primary))
            split.setCheckable(True)
            split.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            split.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            split.setMinimumHeight(30)
            split.setProperty("tool_name", primary)

            split.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            menu = QMenu(split)
            for name in names:
                action = menu.addAction(self._label_for(name))
                sc = TOOL_SHORTCUTS.get(name)
                if sc:
                    action.setShortcut(QKeySequence(sc))
                action.triggered.connect(
                    lambda _=False, n=name, s=split: self._on_category_pick(n, s)
                )
            split.setMenu(menu)

            split.clicked.connect(
                lambda _=False, s=split: self.tool_selected.emit(s.property("tool_name") or s.text())
            )

            self._group.addButton(split)
            self._buttons[primary] = split
            count = self._grid.count()
            self._grid.addWidget(split, count // 2, count % 2)
            self._install_shortcut(primary, split)

            if first_btn is None:
                first_btn = split
                first_name = primary

        if first_btn is not None:
            first_btn.setChecked(True)
            self._active_tool_name = first_name

    def _on_category_pick(self, name: str, split_btn: "QToolButton") -> None:
        """Switch the split-button label to ``name`` and emit tool_selected."""
        # Remap _buttons so the new active tool name resolves to this button.
        old_key = next((k for k, v in self._buttons.items() if v is split_btn), None)
        if old_key and old_key != name:
            self._buttons.pop(old_key)
            self._buttons[name] = split_btn
        split_btn.setText(self._label_for(name))
        split_btn.setToolTip(self._tooltip_for(name))
        split_btn.setProperty("tool_name", name)
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
        brush_name = self._name_for_id("brush")
        if brush_name is None:
            return
        btn = self._buttons.get(brush_name)
        if btn is not None:
            btn.setChecked(True)
        self.tool_selected.emit(brush_name)

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
