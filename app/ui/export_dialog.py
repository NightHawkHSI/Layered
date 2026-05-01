"""Export options dialog.

Lets the user pick:
  * format (PNG, WEBP, TIFF, DDS, BMP, JPG)
  * mode (single composite vs per-layer with manifest)
  * alpha behavior (keep / flatten with color)
  * output path (file for composite, folder for per-layer)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..export import FORMATS


class ExportDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, default_dir: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.resize(480, 280)
        self._default_dir = str(default_dir or Path.cwd())
        self._flatten_bg = (255, 255, 255)

        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FORMATS.keys()))
        self.format_combo.currentTextChanged.connect(self._on_format_changed)

        self.mode_composite = QRadioButton("Single composite image")
        self.mode_layers = QRadioButton("Per-layer with manifest.json")
        self.mode_composite.setChecked(True)
        self.mode_composite.toggled.connect(self._update_path_label)

        self.alpha_check = QCheckBox("Preserve alpha channel (when format supports it)")
        self.alpha_check.setChecked(True)

        self.bg_btn = QPushButton("Flatten color: #FFFFFF")
        self.bg_btn.clicked.connect(self._pick_bg)

        self.path_edit = QLineEdit()
        self.path_btn = QPushButton("Browse…")
        self.path_btn.clicked.connect(self._pick_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.path_btn)

        form = QFormLayout()
        form.addRow("Format:", self.format_combo)
        form.addRow("Mode:", self.mode_composite)
        form.addRow("", self.mode_layers)
        form.addRow("Alpha:", self.alpha_check)
        form.addRow("Flatten:", self.bg_btn)
        self.path_label = QLabel("Output file:")
        form.addRow(self.path_label, path_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(buttons)

        self._on_format_changed(self.format_combo.currentText())

    def _on_format_changed(self, fmt: str) -> None:
        _, supports_alpha = FORMATS[fmt]
        self.alpha_check.setEnabled(supports_alpha)
        self.bg_btn.setEnabled(not supports_alpha or not self.alpha_check.isChecked())
        self.alpha_check.toggled.connect(lambda v: self.bg_btn.setEnabled(not v or not FORMATS[fmt][1]))

    def _update_path_label(self) -> None:
        if self.mode_composite.isChecked():
            self.path_label.setText("Output file:")
        else:
            self.path_label.setText("Output folder:")

    def _pick_bg(self) -> None:
        r, g, b = self._flatten_bg
        c = QColorDialog.getColor(QColor(r, g, b), self, "Flatten background")
        if c.isValid():
            self._flatten_bg = (c.red(), c.green(), c.blue())
            self.bg_btn.setText(f"Flatten color: {c.name().upper()}")

    def _pick_path(self) -> None:
        fmt = self.format_combo.currentText()
        if self.mode_composite.isChecked():
            ext = fmt.lower()
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save composite",
                str(Path(self._default_dir) / f"composite.{ext}"),
                f"{fmt} (*.{ext})",
            )
        else:
            path = QFileDialog.getExistingDirectory(self, "Export layers to folder", self._default_dir)
        if path:
            self.path_edit.setText(path)

    def options(self) -> dict:
        return {
            "format": self.format_combo.currentText(),
            "per_layer": self.mode_layers.isChecked(),
            "keep_alpha": self.alpha_check.isChecked(),
            "flatten_bg": self._flatten_bg,
            "path": self.path_edit.text().strip(),
        }
