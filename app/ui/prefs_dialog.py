"""Preferences dialog — theme, UI accent colour + startup behaviour."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.app_ui.preferences import Preferences


class _ColorSwatch(QPushButton):
    """Square push-button that shows the current colour and opens a picker."""

    def __init__(self, hex_color: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 28)
        self.set_color(hex_color)
        self.clicked.connect(self._pick)

    def set_color(self, hex_color: str) -> None:
        self._hex = hex_color
        self.setStyleSheet(
            f"background-color:{hex_color}; border:1px solid #555; border-radius:3px;"
        )
        self.setToolTip(hex_color)

    def color(self) -> str:
        return self._hex

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._hex), self, "Choose accent colour")
        if c.isValid():
            self.set_color(c.name())


class PrefsDialog(QDialog):
    """Edit and preview user preferences."""

    def __init__(self, prefs: Preferences, apply_fn, apply_theme_fn, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(360)
        self._prefs          = prefs
        self._apply_fn       = apply_fn        # callable(hex) — live preview
        self._apply_theme_fn = apply_theme_fn  # callable(name) — live preview

        root = QVBoxLayout(self)
        root.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        # -- theme ----------------------------------------------------------
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        self._theme_combo.setCurrentText(
            "Light" if prefs.theme == "light" else "Dark"
        )
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        form.addRow("Theme:", self._theme_combo)

        # -- accent colour --------------------------------------------------
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

        # -- restore session ------------------------------------------------
        self._restore_cb = QCheckBox("Restore open projects on startup")
        self._restore_cb.setChecked(prefs.restore_session)
        form.addRow("On launch:", self._restore_cb)

        root.addLayout(form)
        root.addStretch()

        # -- buttons --------------------------------------------------------
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
        )
        btns.accepted.connect(self._commit)
        btns.rejected.connect(self._revert)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply
        )
        root.addWidget(btns)

        # Keep the values active when the dialog opened so we can restore
        # them if the user presses Cancel after a live preview.
        self._original_accent = prefs.accent_color
        self._original_theme  = prefs.theme

    # -- internal helpers ---------------------------------------------------

    def _on_theme_changed(self, label: str) -> None:
        self._apply_theme_fn(label.lower())   # live preview

    def _update_preview(self, hex_color: str) -> None:
        c = QColor(hex_color)
        # Pick a contrasting label colour
        luma = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        text = "#ffffff" if luma < 0.55 else "#000000"
        self._preview.setStyleSheet(
            f"background-color:{hex_color}; color:{text}; "
            f"border-radius:3px; font-size:11px; padding:2px 6px;"
        )
        self._preview.setText(hex_color.upper())

    def _on_swatch_changed(self) -> None:
        hex_color = self._swatch.color()
        self._update_preview(hex_color)
        self._apply_fn(hex_color)           # live preview

    def _reset_accent(self) -> None:
        default = "#2196f3"
        self._swatch.set_color(default)
        self._update_preview(default)
        self._apply_fn(default)

    # -- button handlers ----------------------------------------------------

    def _apply(self) -> None:
        self._prefs.accent_color    = self._swatch.color()
        self._prefs.restore_session = self._restore_cb.isChecked()
        self._prefs.theme           = self._theme_combo.currentText().lower()
        # _apply_theme_fn reinstalls the base stylesheet *and* the accent.
        self._apply_theme_fn(self._prefs.theme)
        self._prefs.save()

    def _commit(self) -> None:
        self._apply()
        self.accept()

    def _revert(self) -> None:
        # Undo live previews: theme first (it also re-lays the accent),
        # then the accent in case only the colour was being previewed.
        self._apply_theme_fn(self._original_theme)
        self._apply_fn(self._original_accent)
        self.reject()
