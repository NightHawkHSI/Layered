"""Import options dialog.

Shown for both drag-and-drop imports and `File → Open as Layer`. Three
button choices (New Project / Add Layer / Replace) plus per-import options
(center on canvas, scale to fit if larger than canvas).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DropActionDialog(QDialog):
    NEW_PROJECT = "new_project"
    ADD_LAYER = "add_layer"
    REPLACE = "replace"

    def __init__(
        self,
        file_count: int,
        parent: Optional[QWidget] = None,
        *,
        show_new_project: bool = True,
        show_replace: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle("Import image" + ("s" if file_count > 1 else ""))
        self.setMinimumWidth(360)
        self._choice = ""

        self.center_check = QCheckBox("Center on canvas")
        self.center_check.setChecked(True)
        self.scale_check = QCheckBox("Scale to fit if larger than canvas")
        self.scale_check.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Importing {file_count} image{'s' if file_count > 1 else ''}. Choose an action:"
        ))

        if show_new_project:
            layout.addWidget(self._make_button("Open as new project", self.NEW_PROJECT))
        layout.addWidget(self._make_button("Add as new layer in current project", self.ADD_LAYER))
        if show_replace:
            layout.addWidget(self._make_button("Replace current canvas", self.REPLACE))

        layout.addSpacing(8)
        layout.addWidget(self.center_check)
        layout.addWidget(self.scale_check)
        layout.addStretch(1)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

    def _make_button(self, label: str, choice: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setMinimumHeight(36)
        btn.clicked.connect(lambda _=False, c=choice: self._pick(c))
        return btn

    def _pick(self, choice: str) -> None:
        self._choice = choice
        self.accept()

    def selected(self) -> str:
        return self._choice

    def options(self) -> dict:
        return {
            "center": self.center_check.isChecked(),
            "scale_to_fit": self.scale_check.isChecked(),
        }
