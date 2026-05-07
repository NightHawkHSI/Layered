# coding: utf-8
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)
from ..preferences import Preferences


class _ColorSwatch(QPushButton):
    def __init__(self, hex_color, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 28)
        self.set_color(hex_color)
        self.clicked.connect(self._pick)

    def set_color(self, hex_color):
        self._hex = hex_color
        self.setStyleSheet(
            "background-color:" + hex_color + ";"
            "border:1px solid #555;border-radius:3px;"
        )
        self.setToolTip(hex_color)

    def color(self):
        return self._hex

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._hex), self, "Choose accent colour")
        if c.isValid():
            self.set_color(c.name())


class PrefsDialog(QDialog):
    def __init__(self, prefs, apply_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(360)
        self._prefs = prefs
        self._apply_fn = apply_fn
        root = QVBoxLayout(self)
        root.setSpacing(14)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        accent_row = QHBoxLayout()
        self._swatch = _ColorSwatch(prefs.accent_color)
        self._swatch.clicked.connect(self._on_swatch_changed)
        self._preview = QLabel()
        self._preview.setFixedHeight(28)
        self._preview.setMinimumWidth(140)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_preview(prefs.accent_color)
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedWidth(54)
        reset_btn.clicked.connect(self._reset_accent)
        accent_row.addWidget(self._swatch)
        accent_row.addWidget(self._preview, 1)
        accent_row.addWidget(reset_btn)
        form.addRow("UI accent colour:", accent_row)
        self._restore_cb = QCheckBox("Restore open projects on startup")
        self._restore_cb.setChecked(prefs.restore_session)
        form.addRow("On launch:", self._restore_cb)
        root.addLayout(form)
        root.addStretch()
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
        )
        btns.accepted.connect(self._commit)
        btns.rejected.connect(self._revert)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        root.addWidget(btns)
        self._original_accent = prefs.accent_color

    def _update_preview(self, hex_color):
        c = QColor(hex_color)
        luma = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        text = "#ffffff" if luma < 0.55 else "#000000"
        self._preview.setStyleSheet(
            "background-color:" + hex_color + ";color:" + text + ";"
            "border-radius:3px;font-size:11px;padding:2px 6px;"
        )
        self._preview.setText(hex_color.upper())

    def _on_swatch_changed(self):
        hex_color = self._swatch.color()
        self._update_preview(hex_color)
        self._apply_fn(hex_color)

    def _reset_accent(self):
        default = "#2196f3"
        self._swatch.set_color(default)
        self._update_preview(default)
        self._apply_fn(default)

    def _apply(self):
        self._prefs.accent_color = self._swatch.color()
        self._prefs.restore_session = self._restore_cb.isChecked()
        self._apply_fn(self._prefs.accent_color)
        self._prefs.save()

    def _commit(self):
        self._apply()
        self.accept()

    def _revert(self):
        self._apply_fn(self._original_accent)
        self.reject()
