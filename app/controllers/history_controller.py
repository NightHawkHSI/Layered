"""History controller: undo / redo / jump + snapshot application.

Owns every code path that touches the History stack on the active project.
MainWindow connects toolbar actions and the history panel to this
controller; downstream code (paste, fill, layer ops) calls
:py:meth:`HistoryController.commit` whenever it produces an undoable edit.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..main_window import MainWindow


class HistoryController:
    def __init__(self, win: "MainWindow") -> None:
        self.win = win

    # --- panel sync ---------------------------------------------------------

    def refresh_panel(self) -> None:
        h = self.win.current().history
        self.win.history_panel.set_history(
            h.labels(), h.index, h.can_undo(), h.can_redo()
        )
        self.win.undo_action.setEnabled(h.can_undo())
        self.win.redo_action.setEnabled(h.can_redo())

    # --- commits ------------------------------------------------------------

    def commit(self, label: str) -> None:
        """Snapshot the current project state under ``label`` and refresh UI.

        Called from every edit path that produces an undoable result.
        """
        win = self.win
        win.current().commit(label)
        win.layer_panel.refresh()
        win._refresh_tabs()
        self.refresh_panel()
        if hasattr(win, "_plugin_event_listeners"):
            win.emit_event("layer_changed", win.current().stack.active_index)

    # --- snapshot application ----------------------------------------------

    def apply_snapshot(self, snap: Any) -> None:
        """Replace the active project's stack/selection from ``snap`` and
        refresh canvas + panels. Used for undo, redo, and history jump."""
        win = self.win
        proj = win.current()
        proj.stack = snap.stack
        proj.selection = getattr(snap, "selection", None)
        proj.dirty = True
        win.canvas.set_layer_stack(snap.stack, reset_view=False)
        win.layer_panel.stack = snap.stack
        win.layer_panel.refresh()
        win.canvas.refresh()
        win._refresh_tabs()

    # --- user actions -------------------------------------------------------

    def undo(self) -> None:
        snap = self.win.current().history.undo()
        if snap is None:
            return
        self.apply_snapshot(snap)
        self.refresh_panel()
        self.win.statusBar().showMessage(f"Undo: {snap.label}")

    def redo(self) -> None:
        snap = self.win.current().history.redo()
        if snap is None:
            return
        self.apply_snapshot(snap)
        self.refresh_panel()
        self.win.statusBar().showMessage(f"Redo: {snap.label}")

    def jump(self, index: int) -> None:
        snap = self.win.current().history.jump(index)
        if snap is None:
            return
        self.apply_snapshot(snap)
        self.refresh_panel()
        self.win.statusBar().showMessage(f"Jump: {snap.label}")
