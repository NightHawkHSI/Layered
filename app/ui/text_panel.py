"""Live text editing panel.

Wired to `TextTool`: typing in the panel re-renders the current text layer
in real time so the user can keep tweaking the string / size / font /
color until they commit by switching tools or clicking elsewhere.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..tools import ToolContext


class TextPanel(QWidget):
    changed = pyqtSignal()       # any field updated — live re-render
    commit_requested = pyqtSignal()

    def __init__(self, ctx: ToolContext, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.ctx = ctx

        self.text_edit = QLineEdit(ctx.text or "Text")
        self.text_edit.textChanged.connect(self._on_text)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 1024)
        self.size_spin.setValue(int(ctx.text_size))
        self.size_spin.valueChanged.connect(self._on_size)

        self.font_combo = QComboBox()
        self.font_combo.addItem("(default)")
        self.font_combo.addItems(QFontDatabase.families())
        cur = getattr(ctx, "text_font", "")
        if cur:
            idx = self.font_combo.findText(cur)
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)
        self.font_combo.currentTextChanged.connect(self._on_font)

        self.commit_btn = QPushButton("Commit text (Enter)")
        self.commit_btn.clicked.connect(self.commit_requested.emit)

        form = QFormLayout()
        form.addRow("Text:", self.text_edit)
        form.addRow("Size:", self.size_spin)
        form.addRow("Font:", self.font_combo)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Text"))
        layout.addLayout(form)
        layout.addWidget(self.commit_btn)
        layout.addWidget(QLabel("Color = primary swatch"))
        layout.addStretch(1)

    def _on_text(self, s: str) -> None:
        self.ctx.text = s
        self.changed.emit()

    def _on_size(self, v: int) -> None:
        self.ctx.text_size = int(v)
        self.changed.emit()

    def _on_font(self, family: str) -> None:
        self.ctx.text_font = "" if family == "(default)" else family
        self.changed.emit()
