"""Main editor window.

Owns the list of open Projects and switches the canvas/panels to whichever
is active. Hooks up the bottom project tab bar, drag-drop, and the export
dialog.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QSettings, Qt
from PyQt6.QtGui import QAction, QIcon, QImage, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .canvas import Canvas
from .export import export_composite, export_layers
from .history import History
from .image_ops import place_on_canvas
from .layer import Layer, LayerStack
from .logger import get_logger
from .plugin_loader import ActionEntry, FilterEntry, PluginRegistry, load_plugins, shutdown_plugins
from .project import Project
from .project_io import PROJECT_EXT, PROJECT_FILTER, load_project, save_project
from .session import load_session, save_session
from .tools import ToolContext, build_default_tools
from .ui.color_panel import ColorPanel
from .ui.console import LogConsole
from .ui.drop_dialog import DropActionDialog
from .ui.export_dialog import ExportDialog
from .ui.history_panel import HistoryPanel
from .ui.layer_panel import LayerPanel
from .ui.plugin_settings_dialog import PluginSettingsDialog
from .ui.project_tabs import ProjectTabs
from .ui.text_panel import TextPanel
from .ui.tool_panel import ToolPanel


if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
else:
    PROJECT_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = PROJECT_DIR
PLUGINS_DIR = PROJECT_DIR / "Plugins"
SESSION_DIR = PROJECT_DIR / "session"
ICON_PATH = RESOURCE_DIR / "Icon.ico"
if not ICON_PATH.exists():
    ICON_PATH = PROJECT_DIR / "Icon.ico"
ICON_PNG_PATH = RESOURCE_DIR / "Icon.png"
if not ICON_PNG_PATH.exists():
    ICON_PNG_PATH = PROJECT_DIR / "Icon.png"


class NewCanvasDialog(QDialog):
    def __init__(self, parent=None, w: int = 1024, h: int = 768):
        super().__init__(parent)
        self.setWindowTitle("New canvas")
        self.w_spin = QSpinBox()
        self.w_spin.setRange(1, 16384)
        self.w_spin.setValue(w)
        self.h_spin = QSpinBox()
        self.h_spin.setRange(1, 16384)
        self.h_spin.setValue(h)
        form = QFormLayout()
        form.addRow("Width:", self.w_spin)
        form.addRow("Height:", self.h_spin)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(bb)

    def values(self) -> tuple[int, int]:
        return self.w_spin.value(), self.h_spin.value()


class MainWindow(QMainWindow):
    def __init__(self, width: int = 1024, height: int = 768):
        super().__init__()
        self.log = get_logger("ui")
        self.setWindowTitle("Layered")
        self.resize(1400, 900)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        elif ICON_PNG_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PNG_PATH)))

        restored = load_session(SESSION_DIR)
        if restored:
            self.projects: list[Project] = restored
            self.log.info("Restored %d project(s) from session", len(restored))
        else:
            self.projects = [Project.blank(width, height)]
        self.active_project: int = 0
        self._last_export_dir: Optional[Path] = None
        self._last_open_dir: Optional[Path] = None
        self._recent_files: list[Path] = []
        self._recent_menu: Optional[object] = None
        self._docks: dict[str, QDockWidget] = {}
        self._initial_dock_area: dict[str, Qt.DockWidgetArea] = {}
        self._settings = QSettings("Layered", "Layered")
        self._load_recent_files()

        # Allow nested + tabbed dock layouts: panels can be split, stacked,
        # or tabbed anywhere along the four edges, and dropping one onto
        # another tabs them together.
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        # VSCode-style corners: left/right side bars are top-aligned and stop
        # above the bottom panel, which spans the full width.
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        from PyQt6.QtWidgets import QTabWidget
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        # Debounced save so rapid drag/drop events don't thrash QSettings.
        from PyQt6.QtCore import QTimer
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(400)
        self._layout_save_timer.timeout.connect(self._save_layout)

        self.tool_ctx = ToolContext()
        self.tool_ctx.get_selection = lambda: self.current().selection
        self.tool_ctx.set_selection = self._on_selection_changed
        self.tool_ctx.commit_action = self._on_action_committed
        self.tool_ctx.get_canvas_size = lambda: (self.current().stack.width, self.current().stack.height)
        self.tools = build_default_tools(self.tool_ctx)
        if "Picker" in self.tools:
            self.tools["Picker"].on_pick = lambda c: self.color_panel.set_primary(c)  # type: ignore[attr-defined]

        self.canvas = Canvas(self.current().stack)
        self.canvas.selection_provider = lambda: self.current().selection
        self.canvas.set_tool(self.tools["Brush"])
        self.canvas.layer_changed.connect(self._on_canvas_changed)
        self.canvas.action_committed.connect(self._on_action_committed)
        self.canvas.images_dropped.connect(self._on_images_dropped)
        self.setCentralWidget(self.canvas)
        self._copy_buffer = None  # PIL.Image.Image holding last copied region

        # --- panels ---
        self.layer_panel = LayerPanel(self.current().stack)
        self.layer_panel.changed.connect(self._on_layer_panel_changed)
        self.layer_panel.committed.connect(self._on_action_committed)
        self.layer_panel.duplicate_requested.connect(self._on_duplicate_layer)
        self.layer_panel.export_requested.connect(self._on_export_dialog)
        self._add_dock("Layers", self.layer_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.history_panel = HistoryPanel()
        self.history_panel.undo_requested.connect(self._on_undo)
        self.history_panel.redo_requested.connect(self._on_redo)
        self.history_panel.jump_requested.connect(self._on_history_jump)
        history_dock = self._add_dock("History", self.history_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        # Stack History under Layers vertically so both fit at once.
        self.splitDockWidget(self._docks["Layers"], history_dock, Qt.Orientation.Vertical)

        self.tool_panel = ToolPanel(self.tool_ctx, self.tools, layout="tools_dock")
        self.tool_panel.tool_selected.connect(self._on_tool_selected)
        self._add_dock("Tools", self.tool_panel, Qt.DockWidgetArea.LeftDockWidgetArea)

        self._tool_settings_bar = QToolBar("Tool settings", self)
        self._tool_settings_bar.setObjectName("toolbar.tool_settings")
        self._tool_settings_bar.setMovable(True)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._tool_settings_bar)
        self.tool_panel.populate_settings_toolbar(self._tool_settings_bar)

        self._tool_settings_bar.topLevelChanged.connect(lambda *_: self._schedule_layout_save())
        self._tool_settings_bar.visibilityChanged.connect(lambda *_: self._schedule_layout_save())

        self.color_panel = ColorPanel(self.tool_ctx)
        colors_dock = self._add_dock("Colors", self.color_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        # Place Tools above Colors on the left so brush buttons are always visible.
        self.splitDockWidget(self._docks["Tools"], colors_dock, Qt.Orientation.Vertical)
        # Live text-edit panel — tab it with Colors to save space.
        self.text_panel = TextPanel(self.tool_ctx)
        self.text_panel.changed.connect(self._on_text_changed)
        self.text_panel.commit_requested.connect(self._on_text_commit)
        text_dock = self._add_dock("Text", self.text_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tabifyDockWidget(colors_dock, text_dock)
        colors_dock.raise_()
        # Color changes also retrigger live text re-render.
        self.color_panel.primary_changed.connect(lambda *_: self._on_text_changed())

        self.console = LogConsole()
        self._add_dock("Console", self.console, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.project_tabs = ProjectTabs()
        self.project_tabs.project_activated.connect(self._switch_project)
        self.project_tabs.project_closed.connect(self._close_project)
        self.project_tabs.project_saved.connect(self._save_project)
        self.project_tabs.new_requested.connect(self._on_new)
        self._add_dock("Projects", self.project_tabs, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        # --- plugins ---
        self.plugins: PluginRegistry = load_plugins(
            PLUGINS_DIR, self.current().stack, self.tool_ctx, self.canvas
        )
        for name, tool in self.plugins.tools.items():
            self.tools[name] = tool
            self.tool_panel.add_tool_button(name)

        self._build_menus()
        self._refresh_tabs()
        # Snapshot the default layout so users can return to it.
        self._default_state = self.saveState()
        self._default_geometry = self.saveGeometry()
        self._restore_layout()
        self.log.info("Main window initialized: %dx%d", width, height)

    def _restore_layout(self) -> None:
        geom = self._settings.value("window/geometry")
        state = self._settings.value("window/state")
        if geom is not None:
            self.restoreGeometry(geom)
        if state is not None:
            self.restoreState(state)

    def _save_layout(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())

    def _reset_layout(self) -> None:
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)
        for dock in self._docks.values():
            dock.show()
        self._tool_settings_bar.show()
        self._save_layout()

    def _toggle_dock(self, title: str, visible: bool) -> None:
        dock = self._docks.get(title)
        if dock is None:
            return
        if visible:
            # If the dock was floating-and-closed or stuck in a zero-size
            # area, re-attach to its initial dock area before showing.
            if not self.dockWidgetArea(dock) or dock.isFloating():
                area = self._initial_dock_area.get(title, Qt.DockWidgetArea.RightDockWidgetArea)
                self.addDockWidget(area, dock)
            dock.setFloating(False)
            dock.show()
            dock.raise_()
            # Force a sane width if Qt restored a 0-size dock.
            if dock.width() < 80 or dock.height() < 60:
                self.resizeDocks([dock], [260], Qt.Orientation.Horizontal)
                self.resizeDocks([dock], [200], Qt.Orientation.Vertical)
        else:
            dock.hide()

    # --- helpers ---

    def current(self) -> Project:
        return self.projects[self.active_project]

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock.{title}")
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        # Persist layout whenever this dock is moved, resized into a new
        # area, floated, or tabbed. Debounced so a single drag doesn't fire
        # dozens of QSettings writes.
        dock.dockLocationChanged.connect(lambda *_: self._schedule_layout_save())
        dock.topLevelChanged.connect(lambda *_: self._schedule_layout_save())
        dock.visibilityChanged.connect(lambda *_: self._schedule_layout_save())
        self._docks[title] = dock
        self._initial_dock_area[title] = area
        return dock

    def _schedule_layout_save(self) -> None:
        if hasattr(self, "_layout_save_timer"):
            self._layout_save_timer.start()

    def _build_menus(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction(self._act("New…", self._on_new, "Ctrl+N"))
        file_menu.addAction(self._act("Open Project…", self._on_open_project))
        file_menu.addAction(self._act("Open Image…", self._on_open, "Ctrl+O"))
        file_menu.addAction(self._act("Open as Layer…", self._on_open_layer))
        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._refresh_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self._act("Save Project", self._on_save_project_file, "Ctrl+S"))
        file_menu.addAction(self._act("Save Project As…", self._on_save_project_as, "Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction(self._act("Export…", self._on_export_dialog, "Ctrl+E"))
        file_menu.addAction(self._act("Quick Save Composite…", self._on_quick_save))
        file_menu.addSeparator()
        file_menu.addAction(self._act("Close Project", self._on_close_current, "Ctrl+W"))
        file_menu.addAction(self._act("Quit", self.close, "Ctrl+Q"))

        edit_menu = mb.addMenu("&Edit")
        self.undo_action = self._act("Undo", self._on_undo, "Ctrl+Z")
        self.redo_action = self._act("Redo", self._on_redo, "Ctrl+Y")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        # Standard alt redo binding.
        redo_alt = QAction("Redo (alt)", self)
        redo_alt.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_alt.triggered.connect(self._on_redo)
        self.addAction(redo_alt)
        edit_menu.addSeparator()
        edit_menu.addAction(self._act("Cut", self._on_cut, "Ctrl+X"))
        edit_menu.addAction(self._act("Copy", self._on_copy, "Ctrl+C"))
        edit_menu.addAction(self._act("Paste", self._on_paste, "Ctrl+V"))
        edit_menu.addAction(self._act("Paste Into Current Layer", self._on_paste_into_current, "Ctrl+Shift+V"))
        edit_menu.addAction(self._act("Select All", self._on_select_all, "Ctrl+A"))
        edit_menu.addAction(self._act("Deselect", self._on_deselect, "Ctrl+D"))
        edit_menu.addAction(self._act("Invert Selection", self._on_invert_selection, "Ctrl+Shift+I"))
        edit_menu.addAction(self._act("Transform Selection", self._on_transform_selection, "Ctrl+T"))
        edit_menu.addSeparator()
        edit_menu.addAction(self._act("Fill with Primary", self._on_fill_primary, "Alt+Backspace"))
        edit_menu.addAction(self._act("Fill with Secondary", self._on_fill_secondary, "Ctrl+Backspace"))
        edit_menu.addSeparator()
        edit_menu.addAction(self._act("Clear Active Layer", self._on_clear_layer))
        edit_menu.addAction(self._act("Delete Active Layer", self._on_delete_layer, "Ctrl+Delete"))

        image_menu = mb.addMenu("&Image")
        image_menu.addAction(self._act("Resize Canvas…", self._on_resize_canvas))
        image_menu.addAction(self._act("Resize Image…", self._on_resize_image))
        image_menu.addAction(self._act("Crop to Selection", self._on_crop_to_selection))
        image_menu.addSeparator()
        image_menu.addAction(self._act("Flip Horizontal", lambda: self._on_flip("horizontal")))
        image_menu.addAction(self._act("Flip Vertical", lambda: self._on_flip("vertical")))
        image_menu.addSeparator()
        image_menu.addAction(self._act("Rotate 90° CW", lambda: self._on_rotate(-90)))
        image_menu.addAction(self._act("Rotate 90° CCW", lambda: self._on_rotate(90)))
        image_menu.addAction(self._act("Rotate 180°", lambda: self._on_rotate(180)))
        image_menu.addSeparator()
        image_menu.addAction(self._act("Flatten Image", self._on_flatten))

        layer_menu = mb.addMenu("&Layer")
        layer_menu.addAction(self._act("New Layer", self._on_new_layer, "Ctrl+Shift+N"))
        layer_menu.addAction(self._act("Duplicate Layer", self._on_duplicate_layer, "Ctrl+J"))
        layer_menu.addAction(self._act("Merge Down", self._on_merge_down, "Ctrl+Shift+E"))

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._act("Fit to Window", self.canvas.fit_to_window, "Ctrl+0"))
        view_menu.addAction(self._act("Zoom 100%", lambda: self._set_zoom(1.0), "Ctrl+1"))
        view_menu.addAction(self._act("Zoom In", lambda: self._zoom_relative(1.25), "Ctrl+="))
        view_menu.addAction(self._act("Zoom Out", lambda: self._zoom_relative(1 / 1.25), "Ctrl+-"))
        # Also bind Ctrl++ explicitly so users on layouts where Plus needs Shift still get it.
        zoom_in_alt = QAction("Zoom In (alt)", self)
        zoom_in_alt.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_alt.triggered.connect(lambda: self._zoom_relative(1.25))
        self.addAction(zoom_in_alt)
        view_menu.addSeparator()
        panels_menu = view_menu.addMenu("Panels")
        # Use a custom toggle (not dock.toggleViewAction()) so we can force a
        # re-attach + resize when bringing a previously-closed panel back —
        # otherwise the dock occasionally restores at zero size and looks
        # missing until the program is restarted.
        for title, dock in self._docks.items():
            act = QAction(title, self)
            act.setCheckable(True)
            act.setChecked(dock.isVisible())
            # `triggered` fires only on user activation; `setChecked` from
            # the visibilityChanged sync below would re-emit `toggled` and
            # cause infinite recursion.
            act.triggered.connect(lambda checked, t=title: self._toggle_dock(t, checked))
            dock.visibilityChanged.connect(
                lambda vis, a=act: a.setChecked(bool(vis))
            )
            panels_menu.addAction(act)
        panels_menu.addSeparator()
        settings_bar_act = QAction("Tool settings bar", self)
        settings_bar_act.setCheckable(True)
        settings_bar_act.setChecked(self._tool_settings_bar.isVisible())
        settings_bar_act.triggered.connect(lambda checked: self._tool_settings_bar.setVisible(checked))
        self._tool_settings_bar.visibilityChanged.connect(settings_bar_act.setChecked)
        panels_menu.addAction(settings_bar_act)
        view_menu.addSeparator()
        view_menu.addAction(self._act("Reset Layout", self._reset_layout))

        filter_menu = mb.addMenu("F&ilters")
        if not self.plugins.filters:
            placeholder = QAction("(none — drop a plugin in /Plugins)", self)
            placeholder.setEnabled(False)
            filter_menu.addAction(placeholder)
        else:
            for name, entry in self.plugins.filters.items():
                label = name + ("…" if entry.settings else "")
                filter_menu.addAction(self._act(
                    label, lambda _=False, n=name, e=entry: self._invoke_filter(n, e)
                ))

        plugins_menu = mb.addMenu("&Plugins")
        if not self.plugins.actions and not self.plugins.plugins:
            placeholder = QAction("(no plugins loaded)", self)
            placeholder.setEnabled(False)
            plugins_menu.addAction(placeholder)
        else:
            for name, entry in self.plugins.actions.items():
                label = name + ("…" if entry.settings else "")
                plugins_menu.addAction(self._act(
                    label, lambda _=False, n=name, e=entry: self._invoke_action(n, e)
                ))
            plugins_menu.addSeparator()
            for loaded in self.plugins.plugins:
                label = f"{loaded.name}"
                if loaded.error:
                    label += f"  ❌  {loaded.error}"
                act = QAction(label, self)
                act.setEnabled(False)
                plugins_menu.addAction(act)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self._act("About", self._on_about))

    def _act(self, name: str, slot, shortcut: Optional[str] = None) -> QAction:
        a = QAction(name, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    def _set_zoom(self, z: float) -> None:
        self.canvas.zoom = z
        self.canvas._auto_fit = False
        self.canvas.update()

    # --- project switching ---

    def _bind_current(self) -> None:
        proj = self.current()
        self.canvas.set_layer_stack(proj.stack)
        self.layer_panel.stack = proj.stack
        self.layer_panel.refresh()
        self._refresh_history_panel()
        text_tool = self.tools.get("Text") if hasattr(self, "tools") else None
        if text_tool is not None:
            text_tool.attach_stack(proj.stack)
        self.setWindowTitle(f"Layered — {proj.display_name()}")

    def _refresh_history_panel(self) -> None:
        h = self.current().history
        self.history_panel.set_history(
            h.labels(), h.index, h.can_undo(), h.can_redo()
        )
        self.undo_action.setEnabled(h.can_undo())
        self.redo_action.setEnabled(h.can_redo())

    def _refresh_tabs(self) -> None:
        from PIL.ImageQt import ImageQt
        from PyQt6.QtGui import QImage, QPixmap

        labels = [p.display_name() for p in self.projects]
        thumbs: list = []
        for p in self.projects:
            try:
                img = p.stack.composite()
                w, h = img.size
                if w == 0 or h == 0:
                    thumbs.append(QPixmap())
                    continue
                scale = min(28 / w, 28 / h)
                tw, th = max(1, int(w * scale)), max(1, int(h * scale))
                small = img.resize((tw, th))
                thumbs.append(QPixmap.fromImage(QImage(ImageQt(small).copy())))
            except Exception:
                thumbs.append(QPixmap())
        self.project_tabs.set_projects(labels, self.active_project, thumbs)

    def _switch_project(self, idx: int) -> None:
        if not (0 <= idx < len(self.projects)):
            return
        self.active_project = idx
        self._bind_current()
        self._refresh_tabs()

    def _close_project(self, idx: int) -> None:
        if not (0 <= idx < len(self.projects)):
            return
        proj = self.projects[idx]
        if proj.dirty:
            r = QMessageBox.question(
                self, "Close project",
                f"'{proj.name}' has unsaved changes. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        self.projects.pop(idx)
        if not self.projects:
            self.projects.append(Project.blank(1024, 768))
            self.active_project = 0
        else:
            self.active_project = max(0, min(self.active_project, len(self.projects) - 1))
            if self.active_project >= idx and self.active_project > 0:
                self.active_project -= 1
        self._bind_current()
        self._refresh_tabs()
        # Persist removal so closed project doesn't reappear next launch.
        try:
            save_session(self.projects, SESSION_DIR)
        except Exception:
            self.log.exception("Failed to save session after close")

    def _save_project(self, idx: int) -> None:
        if not (0 <= idx < len(self.projects)):
            return
        proj = self.projects[idx]
        suggested = proj.path or (self._last_export_dir / Path(proj.name).with_suffix(".png").name if self._last_export_dir else Path(proj.name).with_suffix(".png"))
        path, _ = QFileDialog.getSaveFileName(self, f"Save '{proj.name}'", str(suggested), "PNG (*.png)")
        if not path:
            return
        try:
            export_composite(proj.stack, path, fmt="PNG", keep_alpha=True)
            proj.path = Path(path)
            proj.dirty = False
            self._last_export_dir = Path(path).parent
            self._refresh_tabs()
            self.statusBar().showMessage(f"Saved {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_close_current(self) -> None:
        self._close_project(self.active_project)

    def _mark_dirty(self) -> None:
        proj = self.current()
        if not proj.dirty:
            proj.dirty = True
            self._refresh_tabs()

    # --- slots ---

    def _on_canvas_changed(self) -> None:
        # Intentionally skip layer_panel.refresh / _refresh_tabs during stroke:
        # those rebuild list rows + thumbnails and dominated paint cost.
        # They run again on action_committed.
        proj = self.current()
        if not proj.dirty:
            proj.dirty = True

    def _on_layer_panel_changed(self) -> None:
        self.canvas.refresh()
        self._mark_dirty()

    def _on_action_committed(self, label: str) -> None:
        self.current().commit(label)
        self.layer_panel.refresh()
        self._refresh_tabs()
        self._refresh_history_panel()

    def _apply_snapshot_stack(self, new_stack: LayerStack) -> None:
        proj = self.current()
        proj.stack = new_stack
        proj.dirty = True
        self.canvas.set_layer_stack(new_stack)
        self.layer_panel.stack = new_stack
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._refresh_tabs()

    def _on_undo(self) -> None:
        snap = self.current().history.undo()
        if snap is None:
            return
        self._apply_snapshot_stack(snap.stack)
        self._refresh_history_panel()
        self.statusBar().showMessage(f"Undo: {snap.label}")

    def _on_redo(self) -> None:
        snap = self.current().history.redo()
        if snap is None:
            return
        self._apply_snapshot_stack(snap.stack)
        self._refresh_history_panel()
        self.statusBar().showMessage(f"Redo: {snap.label}")

    def _on_history_jump(self, index: int) -> None:
        snap = self.current().history.jump(index)
        if snap is None:
            return
        self._apply_snapshot_stack(snap.stack)
        self._refresh_history_panel()
        self.statusBar().showMessage(f"Jump: {snap.label}")

    def _on_tool_selected(self, name: str) -> None:
        # Switching away from Text — finalise any in-progress text layer.
        prev = self.canvas.tool
        if prev is self.tools.get("Text") and name != "Text":
            self._on_text_commit()
        tool = self.tools.get(name)
        if tool is None:
            return
        # Generic commit-on-switch: shape tools (and any tool that exposes
        # `commit() -> Optional[str]`) flush their pending state here.
        if (prev is not None and prev is not tool
                and prev is not self.tools.get("Text")
                and hasattr(prev, "commit")):
            try:
                label = prev.commit()
            except Exception:
                label = None
            if label:
                self._on_action_committed(label)
        if name == "Text":
            text_tool = tool
            text_tool.attach_stack(self.current().stack)
            # Surface the Text panel + a tip so the user knows where to edit.
            dock = self._docks.get("Text")
            if dock is not None:
                dock.show()
                dock.raise_()
            self.statusBar().showMessage(
                "Text tool: click on canvas, edit live in the Text panel, switch tools to commit."
            )
        self.canvas.set_tool(tool)
        self.tool_panel.set_active_tool(name)
        self.statusBar().showMessage(f"Tool: {name}")
        self.log.info("Tool selected: %s", name)

    def _on_text_changed(self) -> None:
        text_tool = self.tools.get("Text")
        if text_tool is None:
            return
        # Only re-render when text tool is active and editing a live layer.
        if self.canvas.tool is not text_tool:
            return
        text_tool.rerender()
        self.canvas.refresh()

    def _on_text_commit(self) -> None:
        text_tool = self.tools.get("Text")
        if text_tool is None:
            return
        label = text_tool.commit()
        if label:
            self._on_action_committed(label)

    def _on_new(self) -> None:
        # Pre-fill canvas dims with the size of whatever is on the
        # clipboard. Internal `_copy_buffer` (Ctrl+C of a selection on
        # the active layer) is the most reliable source — it stores the
        # exact cropped PIL image, no system-clipboard round trip — so
        # we check it first. Otherwise fall back to the system clipboard
        # via `_image_from_clipboard` (covers external screenshots /
        # browser images).
        default_w, default_h = 1024, 768
        if self._copy_buffer is not None:
            internal_img = self._copy_buffer[0]
            default_w, default_h = internal_img.width, internal_img.height
        else:
            cb = self._image_from_clipboard()
            if cb is not None:
                default_w, default_h = cb[0].width, cb[0].height
        dlg = NewCanvasDialog(self, w=default_w, h=default_h)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        w, h = dlg.values()
        self.projects.append(Project.blank(w, h))
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()
        self.log.info("New canvas %dx%d", w, h)

    def _on_open(self) -> None:
        start = str(self._last_open_dir) if self._last_open_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open image", start, "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.dds)")
        if not path:
            return
        self._open_image_path(Path(path))

    def _on_open_project(self) -> None:
        start = str(self._last_open_dir) if self._last_open_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, PROJECT_FILTER)
        if not path:
            return
        try:
            proj = load_project(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Open project failed", str(e))
            return
        self.projects.append(proj)
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()
        self._last_open_dir = Path(path).parent
        self._add_recent(Path(path))
        self.log.info("Opened project %s", path)

    def _on_save_project_file(self) -> None:
        proj = self.current()
        if proj.path and str(proj.path).lower().endswith(PROJECT_EXT):
            try:
                save_project(proj, proj.path)
                proj.dirty = False
                self._refresh_tabs()
                self.statusBar().showMessage(f"Saved project: {proj.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save project failed", str(e))
            return
        # No project file yet — fall through to Save As.
        self._on_save_project_as()

    def _on_save_project_as(self) -> None:
        proj = self.current()
        suggested = proj.path or Path(proj.name).with_suffix(PROJECT_EXT)
        if not str(suggested).lower().endswith(PROJECT_EXT):
            suggested = Path(str(suggested)).with_suffix(PROJECT_EXT)
        start = str(suggested)
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", start, PROJECT_FILTER)
        if not path:
            return
        if not path.lower().endswith(PROJECT_EXT):
            path += PROJECT_EXT
        try:
            save_project(proj, Path(path))
            proj.path = Path(path)
            proj.name = Path(path).stem
            proj.dirty = False
            self._add_recent(Path(path))
            self._refresh_tabs()
            self.setWindowTitle(f"Layered — {proj.display_name()}")
            self.statusBar().showMessage(f"Saved project: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save project failed", str(e))

    def _open_recent_path(self, path: Path) -> None:
        """Dispatch a recent-files entry to the right loader by extension."""
        if str(path).lower().endswith(PROJECT_EXT):
            try:
                proj = load_project(path)
            except Exception as e:
                QMessageBox.critical(self, "Open project failed", str(e))
                return
            self.projects.append(proj)
            self.active_project = len(self.projects) - 1
            self._bind_current()
            self._refresh_tabs()
            self._add_recent(path)
            return
        self._open_image_path(path)

    def _open_image_path(self, path: Path) -> None:
        try:
            proj = Project.from_image(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.projects.append(proj)
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()
        self._last_open_dir = path.parent
        self._add_recent(path)
        self.log.info("Opened %s", path)

    def _add_recent(self, path: Path) -> None:
        try:
            p = path.resolve()
        except Exception:
            p = path
        self._recent_files = [p] + [q for q in self._recent_files if q != p]
        del self._recent_files[10:]
        self._refresh_recent_menu()
        self._save_recent_files()

    def _load_recent_files(self) -> None:
        raw = self._settings.value("files/recent", [])
        if isinstance(raw, str):
            raw = [raw]
        elif raw is None:
            raw = []
        out: list[Path] = []
        for s in raw:
            try:
                p = Path(str(s))
                if p.exists():
                    out.append(p)
            except Exception:
                continue
        self._recent_files = out[:10]

    def _save_recent_files(self) -> None:
        self._settings.setValue(
            "files/recent", [str(p) for p in self._recent_files]
        )

    def _refresh_recent_menu(self) -> None:
        if self._recent_menu is None:
            return
        self._recent_menu.clear()
        if not self._recent_files:
            placeholder = QAction("(empty)", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
            return
        for p in self._recent_files:
            label = f"{p.name}  —  {p.parent}"
            self._recent_menu.addAction(self._act(label, lambda _=False, q=p: self._open_recent_path(q)))
        self._recent_menu.addSeparator()
        self._recent_menu.addAction(self._act("Clear Recent", self._clear_recent))

    def _clear_recent(self) -> None:
        self._recent_files = []
        self._save_recent_files()
        self._refresh_recent_menu()

    def _on_open_layer(self) -> None:
        start = str(self._last_open_dir) if self._last_open_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open as layer", start, "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.dds)")
        if not path:
            return
        self._last_open_dir = Path(path).parent
        self._add_recent(Path(path))
        dlg = DropActionDialog(1, self, show_new_project=True, show_replace=False)
        dlg.setWindowTitle("Import options")
        if dlg.exec() != dlg.DialogCode.Accepted:
            # If user cancels the options dialog, fall back to a plain centered import.
            self._add_image_as_layer(Path(path), center=True, scale_to_fit=True)
            return
        opts = dlg.options()
        choice = dlg.selected()
        if choice == DropActionDialog.NEW_PROJECT:
            try:
                proj = Project.from_image(Path(path))
            except Exception as e:
                QMessageBox.critical(self, "Open failed", str(e))
                return
            self.projects.append(proj)
            self.active_project = len(self.projects) - 1
            self._bind_current()
            self._refresh_tabs()
        else:
            self._add_image_as_layer(Path(path), center=opts["center"], scale_to_fit=opts["scale_to_fit"])

    def _add_image_as_layer(self, path: Path, *, center: bool = True, scale_to_fit: bool = True) -> None:
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        stack = self.current().stack
        canvas = place_on_canvas(img, stack.width, stack.height, center=center, scale_to_fit=scale_to_fit)
        stack.add_layer(Layer(name=path.stem, image=canvas))
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Import {path.name}")
        self.log.info("Imported %s as new layer (center=%s, fit=%s)", path, center, scale_to_fit)

    def _replace_canvas_with(self, path: Path, *, center: bool = True, scale_to_fit: bool = True) -> None:
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        proj = self.current()
        # Replace = new canvas sized to the image; center/scale only affect a layer placed inside.
        proj.stack = LayerStack(img.width, img.height)
        if scale_to_fit:
            placed = img  # image fits its own size; nothing to scale
        else:
            placed = img
        layer_canvas = place_on_canvas(placed, img.width, img.height, center=center, scale_to_fit=False)
        proj.stack.add_layer(Layer(name=path.stem, image=layer_canvas))
        proj.name = path.stem
        proj.path = path
        proj.dirty = True
        proj.commit(f"Replace canvas: {path.name}")
        self._bind_current()
        self._refresh_tabs()
        self.log.info("Replaced canvas with %s", path)

    def _on_images_dropped(self, paths: list[Path]) -> None:
        if not paths:
            return
        dlg = DropActionDialog(len(paths), self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        action = dlg.selected()
        opts = dlg.options()
        if action == DropActionDialog.NEW_PROJECT:
            for p in paths:
                try:
                    self.projects.append(Project.from_image(p))
                except Exception as e:
                    QMessageBox.warning(self, "Open failed", f"{p}: {e}")
            self.active_project = len(self.projects) - 1
            self._bind_current()
            self._refresh_tabs()
        elif action == DropActionDialog.ADD_LAYER:
            for p in paths:
                self._add_image_as_layer(p, center=opts["center"], scale_to_fit=opts["scale_to_fit"])
        elif action == DropActionDialog.REPLACE:
            self._replace_canvas_with(paths[0], center=opts["center"], scale_to_fit=opts["scale_to_fit"])

    def _on_quick_save(self) -> None:
        proj = self.current()
        suggested = proj.path or (self._last_export_dir / Path(proj.name).with_suffix(".png").name if self._last_export_dir else Path(proj.name).with_suffix(".png"))
        path, _ = QFileDialog.getSaveFileName(self, "Save composite", str(suggested), "PNG (*.png)")
        if not path:
            return
        try:
            export_composite(proj.stack, path, fmt="PNG", keep_alpha=True)
            proj.path = Path(path)
            proj.dirty = False
            self._last_export_dir = Path(path).parent
            self._refresh_tabs()
            self.statusBar().showMessage(f"Saved {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export_dialog(self) -> None:
        proj = self.current()
        default = self._last_export_dir or (proj.path.parent if proj.path else None)
        dlg = ExportDialog(self, default_dir=default)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        opts = dlg.options()
        if not opts["path"]:
            QMessageBox.warning(self, "Export", "No output path selected.")
            return
        out_path = Path(opts["path"])
        self._last_export_dir = out_path if out_path.is_dir() else out_path.parent
        try:
            if opts["per_layer"]:
                export_layers(
                    proj.stack,
                    opts["path"],
                    fmt=opts["format"],
                    keep_alpha=opts["keep_alpha"],
                    flatten_bg=opts["flatten_bg"],
                )
                self.statusBar().showMessage(f"Exported {len(proj.stack)} layers to {opts['path']}")
            else:
                export_composite(
                    proj.stack,
                    opts["path"],
                    fmt=opts["format"],
                    keep_alpha=opts["keep_alpha"],
                    flatten_bg=opts["flatten_bg"],
                )
                self.statusBar().showMessage(f"Exported composite to {opts['path']}")
            proj.dirty = False
            self._refresh_tabs()
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_resize_canvas(self) -> None:
        stack = self.current().stack
        w, ok = QInputDialog.getInt(self, "Resize canvas", "Width:", stack.width, 1, 16384)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "Resize canvas", "Height:", stack.height, 1, 16384)
        if not ok:
            return
        stack.resize_canvas(w, h)
        self.canvas.fit_to_window()
        self._mark_dirty()
        self._on_action_committed(f"Resize {w}×{h}")
        self.log.info("Canvas resized to %dx%d", w, h)

    def _on_delete_layer(self) -> None:
        stack = self.current().stack
        if stack.active is None:
            return
        name = stack.active.name
        stack.remove_active()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Delete {name}")

    # --- selection / fill QoL ---

    def _on_invert_selection(self) -> None:
        from .project import Selection
        proj = self.current()
        cw, ch = proj.stack.width, proj.stack.height
        if proj.selection is None:
            proj.selection = Selection.rect(0, 0, cw, ch, cw, ch)
            self.canvas.refresh()
            return
        sel_mask = proj.selection.mask
        if sel_mask.size != (cw, ch):
            full = Image.new("L", (cw, ch), 0)
            full.paste(sel_mask, (0, 0))
            sel_mask = full
        inverted = sel_mask.point(lambda v: 255 - v)
        bb = inverted.getbbox()
        if bb is None:
            proj.selection = None
        else:
            proj.selection = Selection(bbox=bb, mask=inverted)
        self.canvas.refresh()

    def _on_transform_selection(self) -> None:
        proj = self.current()
        if proj.selection is None:
            self.statusBar().showMessage("No selection to transform.")
            return
        if "Sel Transform" not in self.tools:
            return
        self._on_tool_selected("Sel Transform")

    def _fill_selection_with(self, color) -> None:
        proj = self.current()
        layer = proj.stack.active
        if layer is None:
            return
        cw, ch = proj.stack.width, proj.stack.height
        sel = proj.selection
        from PIL import ImageChops
        ox, oy = layer.offset
        # Build a layer-image-aligned mask from the selection (or full
        # layer if no selection).
        if sel is None:
            layer_mask = Image.new("L", layer.image.size, 255)
        else:
            sel_mask = sel.mask
            if sel_mask.size != (cw, ch):
                full = Image.new("L", (cw, ch), 0)
                full.paste(sel_mask, (0, 0))
                sel_mask = full
            layer_mask = Image.new("L", layer.image.size, 0)
            layer_mask.paste(sel_mask, (-ox, -oy))
        fill_layer = Image.new("RGBA", layer.image.size, color)
        r, g, b, a = fill_layer.split()
        fill_alpha = ImageChops.multiply(a, layer_mask)
        fill_layer = Image.merge("RGBA", (r, g, b, fill_alpha))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src.alpha_composite(fill_layer)
        layer.image = src
        proj.stack.invalidate_cache()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed("Fill")

    def _on_fill_primary(self) -> None:
        self._fill_selection_with(self.tool_ctx.primary_color)

    def _on_fill_secondary(self) -> None:
        self._fill_selection_with(self.tool_ctx.secondary_color)

    # --- image transforms ---

    def _on_resize_image(self) -> None:
        proj = self.current()
        stack = proj.stack
        w, ok = QInputDialog.getInt(self, "Resize image", "Width:", stack.width, 1, 16384)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "Resize image", "Height:", stack.height, 1, 16384)
        if not ok:
            return
        if (w, h) == (stack.width, stack.height):
            return
        sx = w / stack.width
        sy = h / stack.height
        for layer in stack.layers:
            new_w = max(1, int(round(layer.image.width * sx)))
            new_h = max(1, int(round(layer.image.height * sy)))
            layer.image = layer.image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            ox, oy = layer.offset
            layer.offset = (int(round(ox * sx)), int(round(oy * sy)))
        stack.width, stack.height = w, h
        proj.selection = None
        stack.invalidate_cache()
        self.canvas.fit_to_window()
        self._mark_dirty()
        self._on_action_committed(f"Resize image {w}×{h}")

    def _on_crop_to_selection(self) -> None:
        proj = self.current()
        sel = proj.selection
        if sel is None:
            self.statusBar().showMessage("No selection to crop to.")
            return
        bb = sel.bbox
        x0, y0, x1, y1 = bb
        new_w, new_h = x1 - x0, y1 - y0
        if new_w <= 0 or new_h <= 0:
            return
        stack = proj.stack
        for layer in stack.layers:
            ox, oy = layer.offset
            # Translate the layer image so the crop bbox starts at (0,0).
            new_img = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            new_img.paste(layer.image, (ox - x0, oy - y0))
            layer.image = new_img
            layer.offset = (0, 0)
        stack.width, stack.height = new_w, new_h
        proj.selection = None
        stack.invalidate_cache()
        self.canvas.fit_to_window()
        self._mark_dirty()
        self._on_action_committed(f"Crop to selection {new_w}×{new_h}")

    def _on_flip(self, direction: str) -> None:
        proj = self.current()
        stack = proj.stack
        cw, ch = stack.width, stack.height
        for layer in stack.layers:
            ox, oy = layer.offset
            lw, lh = layer.image.size
            if direction == "horizontal":
                layer.image = layer.image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                layer.offset = (cw - ox - lw, oy)
            else:
                layer.image = layer.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                layer.offset = (ox, ch - oy - lh)
        proj.selection = None
        stack.invalidate_cache()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Flip {direction}")

    def _on_rotate(self, degrees: int) -> None:
        proj = self.current()
        stack = proj.stack
        cw, ch = stack.width, stack.height
        new_cw, new_ch = (cw, ch) if degrees == 180 else (ch, cw)
        for layer in stack.layers:
            ox, oy = layer.offset
            lw, lh = layer.image.size
            if degrees == 90:  # CCW
                layer.image = layer.image.transpose(Image.Transpose.ROTATE_90)
                layer.offset = (oy, cw - ox - lw)
            elif degrees == -90:  # CW
                layer.image = layer.image.transpose(Image.Transpose.ROTATE_270)
                layer.offset = (ch - oy - lh, ox)
            else:  # 180
                layer.image = layer.image.transpose(Image.Transpose.ROTATE_180)
                layer.offset = (cw - ox - lw, ch - oy - lh)
        stack.width, stack.height = new_cw, new_ch
        proj.selection = None
        stack.invalidate_cache()
        self.canvas.fit_to_window()
        self._mark_dirty()
        label = {90: "CCW", -90: "CW", 180: "180°"}.get(degrees, str(degrees))
        self._on_action_committed(f"Rotate {label}")

    def _on_flatten(self) -> None:
        proj = self.current()
        stack = proj.stack
        if not stack.layers:
            return
        composite = stack.composite()
        # Replace the entire layer list with one Background containing the composite.
        stack.layers = [Layer(name="Background", image=composite, offset=(0, 0))]
        stack.active_index = 0
        stack.invalidate_cache()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed("Flatten image")

    # --- layer QoL ---

    def _on_new_layer(self) -> None:
        stack = self.current().stack
        stack.add_layer()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed("New layer")

    def _on_duplicate_layer(self) -> None:
        stack = self.current().stack
        layer = stack.active
        if layer is None:
            return
        dup = Layer(
            name=f"{layer.name} copy",
            image=layer.image.copy(),
            visible=layer.visible,
            opacity=layer.opacity,
            blend_mode=layer.blend_mode,
            offset=layer.offset,
            locked=layer.locked,
            group=layer.group,
        )
        stack.layers.insert(stack.active_index + 1, dup)
        stack.active_index += 1
        stack.invalidate_cache()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Duplicate {layer.name}")

    def _on_merge_down(self) -> None:
        stack = self.current().stack
        if stack.active_index <= 0 or stack.active_index >= len(stack.layers):
            self.statusBar().showMessage("Nothing to merge down to.")
            return
        top = stack.layers[stack.active_index]
        bottom = stack.layers[stack.active_index - 1]
        cw, ch = stack.width, stack.height
        # Composite top-onto-bottom in canvas space, then write into bottom.
        from .blending import composite as np_composite
        import numpy as np
        bottom_canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        bottom_canvas.paste(bottom.image, bottom.offset)
        top_canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        top_canvas.paste(top.image, top.offset)
        if top.blend_mode == "Normal" and top.opacity >= 0.999 and top.visible:
            merged = Image.alpha_composite(bottom_canvas, top_canvas)
        elif not top.visible or top.opacity <= 0:
            merged = bottom_canvas
        else:
            base_arr = np.asarray(bottom_canvas, dtype=np.float32) / 255.0
            top_arr = np.asarray(top_canvas, dtype=np.float32) / 255.0
            out = np_composite(base_arr, top_arr, top.blend_mode, top.opacity)
            merged = Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8), mode="RGBA")
        bottom.image = merged
        bottom.offset = (0, 0)
        stack.layers.pop(stack.active_index)
        stack.active_index -= 1
        stack.invalidate_cache()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed("Merge down")

    # --- view ---

    def _zoom_relative(self, factor: float) -> None:
        new_zoom = max(0.05, min(32.0, self.canvas.zoom * factor))
        self.canvas.zoom = new_zoom
        self.canvas._auto_fit = False
        self.canvas.update()

    def _on_clear_layer(self) -> None:
        stack = self.current().stack
        layer = stack.active
        if layer is None:
            return
        layer.image = Image.new("RGBA", (stack.width, stack.height), (0, 0, 0, 0))
        stack.invalidate_cache()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Clear {layer.name}")

    def _prompt_settings(self, title: str, entry) -> Optional[dict]:
        if not entry.settings:
            return {}
        dlg = PluginSettingsDialog(title, entry.settings, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return None
        return dlg.values()

    def _invoke_filter(self, name: str, entry: FilterEntry) -> None:
        layer = self.current().stack.active
        if layer is None:
            QMessageBox.information(self, "No active layer", "Select a layer first.")
            return
        kwargs = self._prompt_settings(name, entry)
        if kwargs is None:
            return
        try:
            new_img = entry.fn(layer.image.copy(), **kwargs)
        except Exception as e:
            QMessageBox.critical(self, "Filter failed", str(e))
            return
        if new_img is None or not isinstance(new_img, Image.Image):
            QMessageBox.warning(self, "Filter", "Filter returned no image.")
            return
        layer.replace_image(new_img)
        self.current().stack.invalidate_cache()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Filter: {name}")

    def _invoke_action(self, name: str, entry: ActionEntry) -> None:
        kwargs = self._prompt_settings(name, entry)
        if kwargs is None:
            return
        try:
            entry.fn(**kwargs)
        except Exception as e:
            QMessageBox.critical(self, "Action failed", str(e))
            return
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Action: {name}")

    # --- selection / clipboard ---

    def _on_selection_changed(self, sel) -> None:
        proj = self.current()
        proj.selection = sel
        self.canvas.refresh()

    def _on_select_all(self) -> None:
        from .project import Selection
        proj = self.current()
        cw, ch = proj.stack.width, proj.stack.height
        proj.selection = Selection.rect(0, 0, cw, ch, cw, ch)
        self.canvas.refresh()

    def _on_deselect(self) -> None:
        proj = self.current()
        if proj.selection is None:
            return
        proj.selection = None
        self.canvas.refresh()

    def _selection_or_full(self):
        from .project import Selection
        proj = self.current()
        if proj.selection is not None:
            return proj.selection
        cw, ch = proj.stack.width, proj.stack.height
        return Selection.rect(0, 0, cw, ch, cw, ch)

    def _on_copy(self) -> None:
        proj = self.current()
        layer = proj.stack.active
        if layer is None:
            return
        sel = self._selection_or_full()
        bb = sel.bbox
        ox, oy = layer.offset
        cw, ch = proj.stack.width, proj.stack.height
        # Build the canvas-aligned layer buffer in NumPy. PIL's `paste`
        # has version-dependent behaviour when pasting an RGBA image
        # without an explicit mask (some Pillow builds implicitly use
        # the source alpha as a mask, which premultiplies RGB into the
        # transparent destination); doing the blit by hand keeps RGBA
        # exactly as-is so semi-transparent and anti-aliased pixels
        # round-trip losslessly.
        import numpy as np
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src_arr = np.asarray(src, dtype=np.uint8)
        sh, sw = src_arr.shape[:2]
        canvas_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
        y0 = max(0, oy); y1 = min(ch, oy + sh)
        x0 = max(0, ox); x1 = min(cw, ox + sw)
        if y1 > y0 and x1 > x0:
            canvas_arr[y0:y1, x0:x1] = src_arr[y0 - oy:y1 - oy, x0 - ox:x1 - ox]

        bx0, by0, bx1, by1 = bb
        bx0 = max(0, min(cw, bx0)); bx1 = max(0, min(cw, bx1))
        by0 = max(0, min(ch, by0)); by1 = max(0, min(ch, by1))
        if bx1 <= bx0 or by1 <= by0:
            return
        crop_arr = canvas_arr[by0:by1, bx0:bx1].copy()

        sel_mask = sel.mask
        if sel_mask.size != (cw, ch):
            full = Image.new("L", (cw, ch), 0)
            full.paste(sel_mask, (0, 0))
            sel_mask = full
        mask_arr = np.asarray(sel_mask, dtype=np.uint16)[by0:by1, bx0:bx1]
        crop_arr[..., 3] = (
            crop_arr[..., 3].astype(np.uint16) * mask_arr // 255
        ).astype(np.uint8)
        cropped = Image.fromarray(crop_arr, mode="RGBA")

        # Tag the buffer with the source project so a later paste can
        # tell whether we're pasting back into the same project (keep
        # original bbox position) or into a different one (treat like an
        # external image paste — ask for size mode).
        self._copy_buffer = (cropped, (bx0, by0, bx1, by1), proj)
        self._push_image_to_clipboard(cropped)
        self.statusBar().showMessage(f"Copied {bx1-bx0}×{by1-by0} region")

    def _push_image_to_clipboard(self, img: Image.Image) -> None:
        cb = QApplication.clipboard()
        if cb is None:
            return
        rgba = img if img.mode == "RGBA" else img.convert("RGBA")
        data = rgba.tobytes("raw", "RGBA")
        qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                      QImage.Format.Format_RGBA8888).copy()
        cb.setImage(qimg)

    def _on_cut(self) -> None:
        self._on_copy()
        proj = self.current()
        layer = proj.stack.active
        if layer is None or self._copy_buffer is None:
            return
        # Erase pixels inside selection mask on active layer.
        sel = self._selection_or_full()
        cw, ch = proj.stack.width, proj.stack.height
        canvas_mask = sel.mask
        if canvas_mask.size != (cw, ch):
            full = Image.new("L", (cw, ch), 0)
            full.paste(canvas_mask, (0, 0))
            canvas_mask = full
        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(canvas_mask, (-ox, -oy))
        from PIL import ImageChops
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        r, g, b, a = src.split()
        keep = layer_mask.point(lambda v: 255 - v)
        a = ImageChops.multiply(a, keep)
        layer.image = Image.merge("RGBA", (r, g, b, a))
        proj.stack.invalidate_cache()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed("Cut selection")

    def _resolve_paste_source(self):
        """Return (img, bb, source_proj, source_label) or (None, None, None, "")."""
        cb = QApplication.clipboard()
        img: Optional[Image.Image] = None
        bb: Optional[tuple[int, int, int, int]] = None
        source_proj: Optional[Project] = None
        source_label = "Pasted"
        if self._copy_buffer is not None:
            img, bb, source_proj = self._copy_buffer
            source_label = "Pasted Selection"
            if cb is not None and not cb.ownsClipboard():
                external = self._image_from_clipboard()
                if external is not None:
                    ext_img, ext_label = external
                    if ext_img.size != img.size:
                        img, source_label = ext_img, ext_label
                        bb = None
                        source_proj = None
        else:
            external = self._image_from_clipboard()
            if external is not None:
                img, source_label = external
        return img, bb, source_proj, source_label

    def _on_paste(self) -> None:
        """Show a cursor-anchored radial menu of paste choices.

        Default options: New Layer / Current Layer / New Project. When
        the clipboard image is bigger than the current canvas, the menu
        expands to the four extend/keep × new/current variants so the
        user controls canvas resizing inline instead of via a separate
        modal dialog.
        """
        proj = self.current()
        if proj is None:
            return
        img, bb, source_proj, source_label = self._resolve_paste_source()
        if img is None:
            return
        cw, ch = proj.stack.width, proj.stack.height
        iw, ih = img.size
        bigger = iw > cw or ih > ch

        labels: list[str] = []
        actions: list = []
        if bigger:
            labels = [
                "New Layer\n(keep canvas)",
                "Current Layer\n(keep canvas)",
                "New Layer\n(extend canvas)",
                "Current Layer\n(extend canvas)",
                "New Project",
            ]
            actions = [
                lambda: self._paste_new_layer(img, bb, source_proj, source_label, mode="crop"),
                lambda: self._paste_into_layer(img, bb, source_proj, source_label, extend=False),
                lambda: self._paste_new_layer(img, bb, source_proj, source_label, mode="extend"),
                lambda: self._paste_into_layer(img, bb, source_proj, source_label, extend=True),
                lambda: self._paste_new_project(img, source_label),
            ]
        else:
            labels = ["New Layer", "Current Layer", "New Project"]
            actions = [
                lambda: self._paste_new_layer(img, bb, source_proj, source_label, mode="anchor"),
                lambda: self._paste_into_layer(img, bb, source_proj, source_label, extend=False),
                lambda: self._paste_new_project(img, source_label),
            ]

        from PyQt6.QtGui import QCursor
        from .ui.radial_menu import RadialMenu
        menu = RadialMenu(labels, self)
        menu.chosen.connect(lambda i: actions[i]())
        menu.show_at(QCursor.pos())
        # Hold a ref so the popup isn't GC'd before it closes.
        self._radial_menu = menu

    # --- paste exec helpers (shared by Ctrl+V radial + Ctrl+Shift+V) ---

    def _paste_new_layer(self, img, bb, source_proj, source_label: str, mode: str) -> None:
        """mode: 'anchor' (same-proj or fits), 'extend', 'crop'."""
        import numpy as np
        proj = self.current()
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        cw, ch = proj.stack.width, proj.stack.height
        iw, ih = img.size

        if source_proj is proj and bb is not None:
            # Same-project, drop pixels back at original bbox.
            img_arr = np.asarray(img, dtype=np.uint8)
            ihx, iwx = img_arr.shape[:2]
            bx, by = bb[0], bb[1]
            new_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
            y0 = max(0, by); y1 = min(ch, by + ihx)
            x0 = max(0, bx); x1 = min(cw, bx + iwx)
            if y1 > y0 and x1 > x0:
                new_arr[y0:y1, x0:x1] = img_arr[y0 - by:y1 - by, x0 - bx:x1 - bx]
            proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
            action_desc = "Paste selection"
        else:
            img_arr = np.asarray(img, dtype=np.uint8)
            ih_a, iw_a = img_arr.shape[:2]
            if mode == "extend":
                new_w, new_h = max(cw, iw), max(ch, ih)
                resized = (new_w, new_h) != (cw, ch)
                if resized:
                    proj.stack.resize_canvas(new_w, new_h)
                new_arr = np.zeros((new_h, new_w, 4), dtype=np.uint8)
                new_arr[:ih_a, :iw_a] = img_arr
                proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
                if resized:
                    self.canvas.fit_to_window()
                action_desc = f"Paste ({source_label}) — extend canvas to {new_w}×{new_h}"
            elif mode == "anchor":
                proj.stack.add_layer(Layer(name=source_label, image=img, offset=(0, 0)))
                action_desc = f"Paste ({source_label}) — anchor full image"
            else:  # crop
                new_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
                ih_c = min(ih_a, ch); iw_c = min(iw_a, cw)
                new_arr[:ih_c, :iw_c] = img_arr[:ih_c, :iw_c]
                proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
                action_desc = f"Paste ({source_label}) — crop to canvas"

        proj.selection = None
        proj.stack.invalidate_cache()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(action_desc)
        self._activate_transform_tool()

    def _paste_into_layer(self, img, bb, source_proj, source_label: str, *, extend: bool) -> None:
        import numpy as np
        proj = self.current()
        layer = proj.stack.active
        if layer is None:
            self.statusBar().showMessage("No active layer to paste into.")
            return
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        if extend:
            cw, ch = proj.stack.width, proj.stack.height
            iw, ih = img.size
            new_w, new_h = max(cw, iw), max(ch, ih)
            if (new_w, new_h) != (cw, ch):
                proj.stack.resize_canvas(new_w, new_h)
                self.canvas.fit_to_window()

        ox, oy = layer.offset
        if source_proj is proj and bb is not None:
            cx, cy = bb[0], bb[1]
        else:
            cx, cy = 0, 0

        img_arr = np.asarray(img, dtype=np.uint8)
        ih, iw = img_arr.shape[:2]
        lw, lh = layer.image.size
        ly = cy - oy; lx = cx - ox
        y0 = max(0, ly); y1 = min(lh, ly + ih)
        x0 = max(0, lx); x1 = min(lw, lx + iw)
        if y1 <= y0 or x1 <= x0:
            self.statusBar().showMessage("Paste falls outside the active layer.")
            return
        buf = np.zeros((lh, lw, 4), dtype=np.uint8)
        buf[y0:y1, x0:x1] = img_arr[y0 - ly:y1 - ly, x0 - lx:x1 - lx]
        pasted = Image.fromarray(buf, mode="RGBA")
        src_layer = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src_layer.alpha_composite(pasted)
        layer.image = src_layer
        proj.selection = None
        proj.stack.invalidate_cache()
        self.layer_panel.refresh()
        self.canvas.refresh()
        self._mark_dirty()
        self._on_action_committed(f"Paste into {layer.name}")

    def _paste_new_project(self, img, source_label: str) -> None:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        w, h = img.size
        proj = Project.blank(w, h, name=source_label)
        # Replace the auto-Background with the pasted image so the new
        # project shows the pixels immediately.
        proj.stack.layers = []
        proj.stack.active_index = -1
        proj.stack.add_layer(Layer(name=source_label, image=img, offset=(0, 0)))
        proj.dirty = True
        self.projects.append(proj)
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()

    def _on_paste_into_current(self) -> None:
        """Quick `Ctrl+Shift+V` shortcut — skip the radial menu and paste
        directly into the active layer.
        """
        img, bb, source_proj, source_label = self._resolve_paste_source()
        if img is None:
            return
        self._paste_into_layer(img, bb, source_proj, source_label, extend=False)

    def _activate_transform_tool(self) -> None:
        if "Transform" not in self.tools:
            return
        self._on_tool_selected("Transform")

    def _ask_paste_mode(self, img_size: tuple[int, int],
                        canvas_size: tuple[int, int]) -> Optional[str]:
        iw, ih = img_size
        cw, ch = canvas_size
        bigger = iw > cw or ih > ch

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Paste Image")
        box.setText(f"Pasted image: {iw} × {ih}\nCanvas: {cw} × {ch}")
        info = "How should the image be placed?\n\n"
        if bigger:
            info += "• Extend Canvas — grow canvas so the full image fits.\n"
        info += (
            "• Anchor Full Image — keep canvas size; layer stores the full image so you "
            "can move/resize it later without losing pixels outside the canvas.\n"
            "• Crop to Canvas — keep canvas size; clip the image to canvas bounds (legacy)."
        )
        box.setInformativeText(info)

        extend_btn = box.addButton("Extend Canvas", QMessageBox.ButtonRole.AcceptRole) if bigger else None
        anchor_btn = box.addButton("Anchor Full Image", QMessageBox.ButtonRole.AcceptRole)
        crop_btn = box.addButton("Crop to Canvas", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)

        box.setDefaultButton(extend_btn if extend_btn is not None else anchor_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked is cancel_btn:
            return None
        if clicked is extend_btn:
            return "extend"
        if clicked is anchor_btn:
            return "anchor"
        if clicked is crop_btn:
            return "crop"
        return None

    def _image_from_clipboard(self) -> Optional[tuple[Image.Image, str]]:
        cb = QApplication.clipboard()
        if cb is None:
            return None
        md = cb.mimeData()
        if md is None:
            return None

        if md.hasImage():
            qimg = cb.image()
            if not qimg.isNull():
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.ReadWrite)
                if qimg.save(buf, "PNG"):
                    from io import BytesIO
                    img = Image.open(BytesIO(bytes(buf.data()))).convert("RGBA")
                    buf.close()
                    return img, "Pasted Image"
                buf.close()

        if md.hasUrls():
            for url in md.urls():
                if not url.isLocalFile():
                    continue
                path = url.toLocalFile()
                try:
                    img = Image.open(path).convert("RGBA")
                except Exception as e:
                    self.log.warning("Paste: could not open %s: %s", path, e)
                    continue
                return img, Path(path).stem or "Pasted Image"

        return None

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Layered",
            "Layered — Python image and asset editor.\n\n"
            "Layered drawing, blend modes, multi-format export, drag-drop, "
            "multi-project tabs, and a Python plugin API.\n"
            "Logs are written to ./logs and crash reports to ./logs/errors.",
        )

    # --- lifecycle ---

    def keyPressEvent(self, event):  # noqa: N802
        # Swallow stray Return/Enter at the window level so it can't
        # trigger an autoDefault QPushButton. If a selection is active,
        # commit-and-clear it instead (Photoshop-like Enter-to-confirm);
        # also flushes any in-progress Sel Transform so the lifted
        # pixels land. Text inputs (QLineEdit, QSpinBox, QPlainTextEdit,
        # etc.) already consume Return/Enter before it bubbles up here.
        from PyQt6.QtCore import Qt as _Qt
        if event.key() in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            self._confirm_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def _confirm_selection(self) -> None:
        proj = self.current()
        # 1) Flush any tool that has its own commit() (Sel Transform's
        #    floating buffer, Text tool's editable layer, shape edit
        #    sessions). The returned label, if any, snapshots history.
        tool = self.canvas.tool
        active_name = None
        for n, t in self.tools.items():
            if t is tool:
                active_name = n
                break
        if tool is not None and hasattr(tool, "commit"):
            try:
                label = tool.commit()
            except Exception:
                label = None
            if label:
                self._on_action_committed(label)
        # 2) Transform tool has no commit() but its handles linger as a
        #    canvas overlay until another tool is picked. Switch back to
        #    Brush so Enter cleanly exits the post-paste transform.
        if active_name in ("Transform", "Sel Transform", "Move") and "Brush" in self.tools:
            self._on_tool_selected("Brush")
        # 3) Drop the marching-ants selection.
        if proj.selection is not None:
            proj.selection = None
            self.canvas.refresh()
            self.statusBar().showMessage("Selection committed")

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._schedule_layout_save()

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        self._schedule_layout_save()

    def closeEvent(self, event):  # noqa: N802
        try:
            self._save_layout()
        except Exception:
            self.log.exception("Failed to save layout")
        try:
            save_session(self.projects, SESSION_DIR)
        except Exception:
            self.log.exception("Failed to save session")
        try:
            shutdown_plugins(self.plugins)
        finally:
            super().closeEvent(event)
