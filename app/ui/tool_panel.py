"""Modern tool panel with large clickable tool cards, search, scrolling,
group headers, and adaptive multi-column layout.

Designed for plugin-heavy paint apps where hundreds of tools/brushes
may exist without becoming difficult to browse.

Features
--------
* Large icon-first tool cards
* 4-column adaptive grid
* Search filter
* Scrollable tools area
* Group sections
* Active tool highlight
* Keyboard shortcuts
* Toolbar + dock support
* Brush settings support
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QRect
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QTextEdit,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QAbstractSpinBox,
)

from app.plugins.tools import Tool, ToolContext

from .slider_field import SliderField


# -----------------------------------------------------------------------------
# Styling
# -----------------------------------------------------------------------------

_ACCENT = "#1a73e8"
_ACCENT_BG = "rgba(26,115,232,0.15)"
_HOVER_BG = "rgba(255,255,255,0.06)"

_COLUMNS = 3  # kept for compat; FlowLayout now drives wrapping
_BTN_MIN = 44
_BTN_MAX = 96

_PANEL_QSS = f"""
QPushButton[tool_btn="true"],
QToolButton[tool_btn="true"] {{
    border: none;
    border-radius: 12px;

    background: transparent;

    padding: 8px;

    text-align: center;

    font-size: 11px;
    font-weight: 500;
}}

QPushButton[tool_btn="true"]:hover,
QToolButton[tool_btn="true"]:hover {{
    background: {_HOVER_BG};
}}

QPushButton[tool_btn="true"]:checked,
QToolButton[tool_btn="true"]:checked {{
    background: {_ACCENT_BG};
    color: {_ACCENT};
    border: 1px solid rgba(26,115,232,0.35);
}}

QLineEdit#toolSearch {{
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid rgba(128,128,128,0.25);
    font-size: 12px;
}}

QLabel#groupHeader {{
    font-size: 10px;
    font-weight: bold;
    color: rgba(180,180,180,0.9);
    padding: 6px 4px;
    letter-spacing: 0.08em;
}}

QLabel#activeToolLabel {{
    font-size: 12px;
    font-weight: bold;
    padding: 8px 10px;
    color: {_ACCENT};
    background: {_ACCENT_BG};
    border-bottom: 1px solid rgba(128,128,128,0.2);
}}
"""


# -----------------------------------------------------------------------------
# Tool icons / shortcuts
# -----------------------------------------------------------------------------
# These module-level dicts are kept ONLY for backwards compatibility with any
# external code that still imports them; they are no longer the source of
# truth. Each Tool subclass declares its own `icon` and `shortcut` class
# attrs, which the host passes to ToolPanel via set_tool_icon() and
# set_tool_shortcut() at registration time.

TOOL_ICONS: dict[str, str] = {}
TOOL_SHORTCUTS: dict[str, str] = {}


# -----------------------------------------------------------------------------
# Flow Layout — wraps children to next row when width runs out
# -----------------------------------------------------------------------------

class _FlowLayout(QLayout):
    """Left-to-right wrapping layout. Reflows on width changes so the
    tool grid auto-arranges no matter where the dock is docked or how
    narrow the user makes it.
    """

    def __init__(self, parent: Optional[QWidget] = None,
                 margin: int = 0, hspacing: int = 8, vspacing: int = 8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing
        self._items: list[QLayoutItem] = []

    def __del__(self):
        while self._items:
            self._items.pop()

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def horizontalSpacing(self) -> int:
        return self._hspace

    def verticalSpacing(self) -> int:
        return self._vspace

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = eff.x()
        y = eff.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspace
            if next_x - self._hspace > eff.right() and line_height > 0:
                x = eff.x()
                y = y + line_height + self._vspace
                next_x = x + hint.width() + self._hspace
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


# -----------------------------------------------------------------------------
# Tool Button
# -----------------------------------------------------------------------------

class _ToolBtn(QPushButton):

    _accent = QColor(_ACCENT)

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)

        self.setProperty("tool_btn", "true")

        self.setCheckable(True)

        self.setMinimumSize(_BTN_MIN, _BTN_MIN)
        self.setMaximumSize(_BTN_MAX, _BTN_MAX)

        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Preferred)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(_BTN_MAX, _BTN_MAX)

    def minimumSizeHint(self) -> QSize:
        return QSize(_BTN_MIN, _BTN_MIN)

    def paintEvent(self, event):

        super().paintEvent(event)

        if self.isChecked():
            p = QPainter(self)

            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            p.fillRect(0, 0, 5, self.height(), self._accent)


# -----------------------------------------------------------------------------
# Group Header
# -----------------------------------------------------------------------------

class _GroupHeader(QLabel):

    def __init__(self, title: str, parent=None):
        super().__init__(title.upper(), parent)

        self.setObjectName("groupHeader")


# -----------------------------------------------------------------------------
# Tool Panel
# -----------------------------------------------------------------------------

class ToolPanel(QWidget):

    tool_selected = pyqtSignal(str)
    tool_order_changed = pyqtSignal(list)

    def __init__(
        self,
        ctx: ToolContext,
        tools: dict[str, Tool],
        parent: Optional[QWidget] = None,
        layout: str = "tools_dock",
    ):

        super().__init__(parent)

        self.ctx = ctx
        self._layout_mode = layout

        self._buttons: dict[str, QPushButton] = {}
        self._shortcuts: dict[str, QShortcut] = {}
        self._tool_groups: dict[str, list[str]] = {}
        # Per-instance icon/shortcut maps populated by Tool class attrs at
        # registration time. Source of truth — no central file required.
        self._icons: dict[str, str] = {}
        self._tool_shortcuts: dict[str, str] = {}
        self._id_to_name: dict[str, str] = {}
        self._tool_order: list[str] = []
        self._brush_presets: dict[str, list] = {}

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self.setStyleSheet(_PANEL_QSS)

        self.setMinimumWidth(_BTN_MAX + 16)

        self._build_ui()

        for name in tools.keys():
            self._add_button(name)

        if self._buttons:
            first = next(iter(self._buttons.values()))
            first.setChecked(True)

    # -------------------------------------------------------------------------

    def _build_ui(self):

        outer = QVBoxLayout(self)

        outer.setContentsMargins(0, 0, 0, 0)

        outer.setSpacing(0)

        # active tool label

        self._active_label = QLabel("No Tool")

        self._active_label.setObjectName("activeToolLabel")

        self._active_label.setWordWrap(True)

        self._active_label.setMinimumWidth(0)

        self._active_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                         QSizePolicy.Policy.Preferred)

        outer.addWidget(self._active_label)

        # search

        self.search = QLineEdit()

        self.search.setObjectName("toolSearch")

        self.search.setPlaceholderText("Search...")

        self.search.setMinimumWidth(0)

        self.search.setSizePolicy(QSizePolicy.Policy.Ignored,
                                  QSizePolicy.Policy.Fixed)

        self.search.textChanged.connect(self._filter_tools)

        outer.addWidget(self.search)

        # scroll area

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        outer.addWidget(scroll)

        # content

        self._content = QWidget()

        cp = QSizePolicy(QSizePolicy.Policy.Preferred,
                         QSizePolicy.Policy.Preferred)
        cp.setHeightForWidth(True)
        self._content.setSizePolicy(cp)

        scroll.setWidget(self._content)

        self._layout = QVBoxLayout(self._content)

        self._layout.setContentsMargins(0, 0, 0, 0)

        self._layout.setSpacing(10)

        # Brush settings live in the per-tool settings toolbar
        # (`MainWindow._tool_settings_bar`), populated from each Tool's
        # build_ui(). The tool dock itself only holds the tool browser.

    # -------------------------------------------------------------------------

    def set_tool_groups(
        self,
        groups: dict[str, list[str]]
    ):

        self._tool_groups = groups

        # Reparent every known button OUT of the layout before tearing it
        # down so Qt doesn't garbage-collect them along with the host
        # widgets. Without this, the buttons in self._buttons become dead
        # references and the next grid.addWidget(btn) segfaults.
        for btn in self._buttons.values():
            btn.setParent(self)

        while self._layout.count():

            item = self._layout.takeAt(0)

            w = item.widget()

            if w:
                w.setParent(None)
                w.deleteLater()

        for group_name, names in groups.items():

            valid = [
                n for n in names
                if n in self._buttons
            ]

            if not valid:
                continue

            header = _GroupHeader(group_name)

            self._layout.addWidget(header)

            grid_host = QWidget()
            gp = QSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Preferred)
            gp.setHeightForWidth(True)
            grid_host.setSizePolicy(gp)

            grid = _FlowLayout(grid_host, margin=0, hspacing=8, vspacing=8)

            for name in valid:

                btn = self._buttons[name]

                grid.addWidget(btn)

            self._layout.addWidget(grid_host)

        self._layout.addStretch(1)

    # -------------------------------------------------------------------------

    def _add_button(self, name: str):

        label = self._label_for(name)

        btn = _ToolBtn(label)

        btn.setToolTip(self._tooltip_for(name))

        btn.clicked.connect(
            lambda _=False, n=name: self._tool_clicked(n)
        )

        self._group.addButton(btn)

        self._buttons[name] = btn
        if name not in self._tool_order:
            self._tool_order.append(name)

        self._install_shortcut(name, btn)

    # -------------------------------------------------------------------------

    def _tool_clicked(self, name: str):

        self._active_label.setText(name)

        self.tool_selected.emit(name)

    # -------------------------------------------------------------------------

    def _label_for(self, name: str) -> str:

        icon = self._icons.get(name) or TOOL_ICONS.get(name, "")

        if icon:
            return f"{icon}\n{name}"

        return name

    # -------------------------------------------------------------------------

    def _tooltip_for(self, name: str) -> str:

        sc = self._tool_shortcuts.get(name) or TOOL_SHORTCUTS.get(name)

        if sc:
            return f"{name} ({sc})"

        return name

    # -------------------------------------------------------------------------

    def _filter_tools(self, text: str):

        text = text.lower().strip()

        for name, btn in self._buttons.items():

            visible = text in name.lower()

            btn.setVisible(visible)

    # -------------------------------------------------------------------------

    def _install_shortcut(self, name: str, btn):

        # Drop any prior binding so re-registration updates cleanly.
        old = self._shortcuts.pop(name, None)
        if old is not None:
            old.setEnabled(False)
            old.deleteLater()

        seq = self._tool_shortcuts.get(name) or TOOL_SHORTCUTS.get(name)

        if not seq:
            return

        sc = QShortcut(QKeySequence(seq), self)

        sc.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )

        sc.activated.connect(
            lambda b=btn, n=name: self._shortcut_trigger(b, n)
        )

        self._shortcuts[name] = sc

    # -------------------------------------------------------------------------

    def _shortcut_trigger(self, btn, name):

        fw = QApplication.focusWidget()

        if isinstance(
            fw,
            (
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QAbstractSpinBox,
            )
        ):
            return

        if isinstance(fw, QComboBox) and fw.isEditable():
            return

        btn.setChecked(True)

        self._tool_clicked(name)

    # -------------------------------------------------------------------------
    # Public API used by MainWindow + plugin loader
    # -------------------------------------------------------------------------

    def register_tool_id(self, tool_id: str, name: str) -> None:
        """Map a stable tool_id to its current display name."""
        if tool_id:
            self._id_to_name[tool_id] = name

    def name_for_id(self, tool_id: str) -> Optional[str]:
        return self._id_to_name.get(tool_id)

    def set_tool_icon(self, name: str, icon: str) -> None:
        """Record this tool's icon glyph (declared on Tool.icon)."""
        if icon:
            self._icons[name] = icon
        else:
            self._icons.pop(name, None)
        btn = self._buttons.get(name)
        if btn is not None:
            btn.setText(self._label_for(name))

    def set_tool_shortcut(self, name: str, seq: str) -> None:
        """Bind a per-tool shortcut declared on Tool.shortcut.

        Pass an empty string to clear the binding. Re-registration drops
        the prior QShortcut and installs the new one.
        """
        if seq:
            self._tool_shortcuts[name] = seq
        else:
            self._tool_shortcuts.pop(name, None)
        btn = self._buttons.get(name)
        if btn is not None:
            btn.setToolTip(self._tooltip_for(name))
            self._install_shortcut(name, btn)

    def add_tool_button(self, name: str) -> None:
        """Create + place a button for `name`. Idempotent."""
        if name in self._buttons:
            return
        self._add_button(name)
        self._tool_order.append(name)
        self._reflow_grid()

    def remove_tool_button(self, name: str) -> None:
        btn = self._buttons.pop(name, None)
        if btn is not None:
            self._group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        sc = self._shortcuts.pop(name, None)
        if sc is not None:
            sc.setEnabled(False)
            sc.deleteLater()
        if name in self._tool_order:
            self._tool_order.remove(name)
        self._icons.pop(name, None)
        self._tool_shortcuts.pop(name, None)
        self._reflow_grid()

    def set_active_tool(self, name: str) -> None:
        btn = self._buttons.get(name)
        if btn is None:
            return
        btn.setChecked(True)
        self._active_label.setText(name)

    def set_tool_categories(self, categories: dict) -> None:
        """Group buttons under category headers.

        `categories` maps category label → list of tool names. Names not in
        any listed category fall under an "Other" section preserving order.
        """
        groups: dict[str, list[str]] = {}
        listed: set[str] = set()
        for cat, names in (categories or {}).items():
            valid = [n for n in names if n in self._buttons]
            if valid:
                groups[cat] = valid
                listed.update(valid)
        leftover = [n for n in self._tool_order if n not in listed]
        if leftover:
            groups.setdefault("Other", []).extend(leftover)
        self.set_tool_groups(groups)

    def set_tool_order(self, order: list) -> None:
        """Reorder buttons by name. Unknown names skipped."""
        if not order:
            return
        valid = [n for n in order if n in self._buttons]
        rest = [n for n in self._tool_order if n not in valid]
        self._tool_order = valid + rest
        self._reflow_grid()

    def set_brush_presets(self, presets: dict) -> None:
        """Register brush presets for the brush-presets dropdown menu."""
        self._brush_presets = presets or {}

    def _apply_preset(self, preset) -> None:
        """Activate a brush preset: set ctx + emit selection.

        Settings widgets live in the per-tool toolbar (built by the
        active Tool's build_ui()), so we only update the shared ctx.
        The toolbar widget reads ctx on next event.
        """
        size = getattr(preset, "size", None)
        if size is not None:
            self.ctx.brush_size = int(size)
        hardness = getattr(preset, "hardness", None)
        if hardness is not None:
            self.ctx.brush_hardness = float(hardness)
        opacity = getattr(preset, "opacity", None)
        if opacity is not None:
            self.ctx.brush_opacity = float(opacity)
        target = getattr(preset, "tool_id", "") or getattr(preset, "tool_name", "")
        name = self._id_to_name.get(target, target)
        if name and name in self._buttons:
            self.set_active_tool(name)
            self.tool_selected.emit(name)

    # -------------------------------------------------------------------------

    def _reflow_grid(self) -> None:
        """If categories are set, leave grouped layout alone; otherwise put
        every known tool into a single grid in `_tool_order`.
        """
        if self._tool_groups:
            return
        # Reparent buttons out before destroying the grid host so they
        # survive the deleteLater on the host (see set_tool_groups).
        for btn in self._buttons.values():
            btn.setParent(self)
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        grid_host = QWidget()
        gp = QSizePolicy(QSizePolicy.Policy.Preferred,
                         QSizePolicy.Policy.Preferred)
        gp.setHeightForWidth(True)
        grid_host.setSizePolicy(gp)
        grid = _FlowLayout(grid_host, margin=0, hspacing=8, vspacing=8)
        for n in self._tool_order:
            btn = self._buttons.get(n)
            if btn is None:
                continue
            grid.addWidget(btn)
        self._layout.addWidget(grid_host)
        self._layout.addStretch(1)