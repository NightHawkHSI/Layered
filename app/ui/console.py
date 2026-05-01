"""In-app log console.

Subscribes to the layered logger via `attach_console_handler` and renders log
records into a scrolling read-only text view. Also exposes Save / Clear.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..logger import attach_console_handler


class LogConsole(QWidget):
    log_line = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        self.text.setMinimumSize(0, 0)

        self.save_btn = QPushButton("Save…")
        self.clear_btn = QPushButton("Clear")
        self.save_btn.clicked.connect(self._on_save)
        self.clear_btn.clicked.connect(self.text.clear)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addWidget(self.save_btn)
        row.addWidget(self.clear_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.log_line.connect(self.text.appendPlainText, Qt.ConnectionType.QueuedConnection)
        attach_console_handler(self.log_line.emit)

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log", "layered-console.log", "Log files (*.log *.txt)")
        if not path:
            return
        Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
