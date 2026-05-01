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
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
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
from .tools import ToolContext, build_default_tools
from .ui.color_panel import ColorPanel
from .ui.console import LogConsole
from .ui.drop_dialog import DropActionDialog
from .ui.export_dialog import ExportDialog
from .ui.history_panel import HistoryPanel
from .ui.layer_panel import LayerPanel
from .ui.plugin_settings_dialog import PluginSettingsDialog
from .ui.project_tabs import ProjectTabs
from .ui.tool_panel import ToolPanel


if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(sys.executable).resolve().parent
else:
    PROJECT_DIR = Path(__file__).resolve().parent.parent
PLUGINS_DIR = PROJECT_DIR / "Plugins"


class MainWindow(QMainWindow):
    def __init__(self, width: int = 1024, height: int = 768):
        super().__init__()
        self.log = get_logger("ui")
        self.setWindowTitle("Layered")
        self.resize(1400, 900)

        self.projects: list[Project] = [Project.blank(width, height)]
        self.active_project: int = 0

        self.tool_ctx = ToolContext()
        self.tools = build_default_tools(self.tool_ctx)
        if "Picker" in self.tools:
            self.tools["Picker"].on_pick = lambda c: self.color_panel.set_primary(c)  # type: ignore[attr-defined]

        self.canvas = Canvas(self.current().stack)
        self.canvas.set_tool(self.tools["Brush"])
        self.canvas.layer_changed.connect(self._on_canvas_changed)
        self.canvas.action_committed.connect(self._on_action_committed)
        self.canvas.images_dropped.connect(self._on_images_dropped)
        self.setCentralWidget(self.canvas)

        # --- panels ---
        self.layer_panel = LayerPanel(self.current().stack)
        self.layer_panel.changed.connect(self._on_layer_panel_changed)
        self.layer_panel.committed.connect(self._on_action_committed)
        self.layer_panel.export_requested.connect(self._on_export_dialog)
        self._add_dock("Layers", self.layer_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.history_panel = HistoryPanel()
        self.history_panel.undo_requested.connect(self._on_undo)
        self.history_panel.redo_requested.connect(self._on_redo)
        self.history_panel.jump_requested.connect(self._on_history_jump)
        self._add_dock("History", self.history_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.tool_panel = ToolPanel(self.tool_ctx, self.tools)
        self.tool_panel.tool_selected.connect(self._on_tool_selected)
        self._add_dock("Tools", self.tool_panel, Qt.DockWidgetArea.LeftDockWidgetArea)

        self.color_panel = ColorPanel(self.tool_ctx)
        self._add_dock("Colors", self.color_panel, Qt.DockWidgetArea.LeftDockWidgetArea)

        self.console = LogConsole()
        self._add_dock("Console", self.console, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.project_tabs = ProjectTabs()
        self.project_tabs.project_activated.connect(self._switch_project)
        self.project_tabs.project_closed.connect(self._close_project)
        self.project_tabs.project_saved.connect(self._save_project)
        self.project_tabs.new_requested.connect(self._on_new)
        tabs_dock = self._add_dock("Projects", self.project_tabs, Qt.DockWidgetArea.BottomDockWidgetArea)
        tabs_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)

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
        self.log.info("Main window initialized: %dx%d", width, height)

    # --- helpers ---

    def current(self) -> Project:
        return self.projects[self.active_project]

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _build_menus(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction(self._act("New…", self._on_new, "Ctrl+N"))
        file_menu.addAction(self._act("Open…", self._on_open, "Ctrl+O"))
        file_menu.addAction(self._act("Open as Layer…", self._on_open_layer))
        file_menu.addSeparator()
        file_menu.addAction(self._act("Export…", self._on_export_dialog, "Ctrl+E"))
        file_menu.addAction(self._act("Quick Save Composite…", self._on_quick_save, "Ctrl+S"))
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
        edit_menu.addAction(self._act("Resize Canvas…", self._on_resize_canvas))
        edit_menu.addAction(self._act("Clear Active Layer", self._on_clear_layer))
        edit_menu.addAction(self._act("Delete Active Layer", self._on_delete_layer, "Ctrl+Delete"))

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self._act("Fit to Window", self.canvas.fit_to_window, "Ctrl+0"))
        view_menu.addAction(self._act("Zoom 100%", lambda: self._set_zoom(1.0), "Ctrl+1"))

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
        self.setWindowTitle(f"Layered — {proj.display_name()}")

    def _refresh_history_panel(self) -> None:
        h = self.current().history
        self.history_panel.set_history(
            h.labels(), h.index, h.can_undo(), h.can_redo()
        )
        self.undo_action.setEnabled(h.can_undo())
        self.redo_action.setEnabled(h.can_redo())

    def _refresh_tabs(self) -> None:
        labels = [p.display_name() for p in self.projects]
        self.project_tabs.set_projects(labels, self.active_project)

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

    def _save_project(self, idx: int) -> None:
        if not (0 <= idx < len(self.projects)):
            return
        proj = self.projects[idx]
        suggested = proj.path or Path(proj.name).with_suffix(".png")
        path, _ = QFileDialog.getSaveFileName(self, f"Save '{proj.name}'", str(suggested), "PNG (*.png)")
        if not path:
            return
        try:
            export_composite(proj.stack, path, fmt="PNG", keep_alpha=True)
            proj.path = Path(path)
            proj.dirty = False
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
        self.layer_panel.refresh()
        self._mark_dirty()

    def _on_layer_panel_changed(self) -> None:
        self.canvas.refresh()
        self._mark_dirty()

    def _on_action_committed(self, label: str) -> None:
        self.current().commit(label)
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
        tool = self.tools.get(name)
        if tool is not None:
            self.canvas.set_tool(tool)
            self.statusBar().showMessage(f"Tool: {name}")
            self.log.info("Tool selected: %s", name)

    def _on_new(self) -> None:
        w, ok = QInputDialog.getInt(self, "New canvas", "Width:", 1024, 1, 16384)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, "New canvas", "Height:", 768, 1, 16384)
        if not ok:
            return
        self.projects.append(Project.blank(w, h))
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()
        self.log.info("New canvas %dx%d", w, h)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.dds)")
        if not path:
            return
        try:
            proj = Project.from_image(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.projects.append(proj)
        self.active_project = len(self.projects) - 1
        self._bind_current()
        self._refresh_tabs()
        self.log.info("Opened %s", path)

    def _on_open_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open as layer", "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.dds)")
        if not path:
            return
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
        suggested = proj.path or Path(proj.name).with_suffix(".png")
        path, _ = QFileDialog.getSaveFileName(self, "Save composite", str(suggested), "PNG (*.png)")
        if not path:
            return
        try:
            export_composite(proj.stack, path, fmt="PNG", keep_alpha=True)
            proj.path = Path(path)
            proj.dirty = False
            self._refresh_tabs()
            self.statusBar().showMessage(f"Saved {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _on_export_dialog(self) -> None:
        proj = self.current()
        dlg = ExportDialog(self, default_dir=proj.path.parent if proj.path else None)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        opts = dlg.options()
        if not opts["path"]:
            QMessageBox.warning(self, "Export", "No output path selected.")
            return
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

    def closeEvent(self, event):  # noqa: N802
        try:
            shutdown_plugins(self.plugins)
        finally:
            super().closeEvent(event)
