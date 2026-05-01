"""History (undo/redo) panel.

Shows a clickable list of every recorded action for the active project. The
current entry is highlighted with a leading marker. Clicking any entry jumps
the project to that snapshot. Buttons mirror Ctrl+Z / Ctrl+Y.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HistoryPanel(QWidget):
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    jump_requested = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_item_clicked)

        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        self.redo_btn.clicked.connect(self.redo_requested.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("History"))
        row = QHBoxLayout()
        row.addWidget(self.undo_btn)
        row.addWidget(self.redo_btn)
        layout.addLayout(row)
        layout.addWidget(self.list, 1)

    def set_history(self, labels: list[str], current_index: int, can_undo: bool, can_redo: bool) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for i, label in enumerate(labels):
            mark = "▶ " if i == current_index else "  "
            item = QListWidgetItem(f"{mark}{i + 1:>2}. {label}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
        if 0 <= current_index < self.list.count():
            self.list.setCurrentRow(current_index)
        self.list.blockSignals(False)
        self.undo_btn.setEnabled(can_undo)
        self.redo_btn.setEnabled(can_redo)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        i = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(i, int):
            self.jump_requested.emit(i)
