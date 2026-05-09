"""Controllers extracted from MainWindow.

Each controller owns one slice of the editor (history, selection, paste,
layers, files). MainWindow holds a reference to each and forwards Qt
signals to controller methods. This keeps the window class focused on
window lifecycle + composition while domain logic lives next to its
data.

Controllers receive the host window as ``win`` and reach back through
it for shared services (current project, canvas, status bar, panels).
That keeps the boundary explicit without inverting every dependency.
"""
from __future__ import annotations

from .history_controller import HistoryController
from .paste_controller import PasteController
from .selection_controller import SelectionController

__all__ = ["HistoryController", "PasteController", "SelectionController"]
