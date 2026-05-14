"""Keyboard shortcut rebinding dialog.

Lists every rebindable menu action and lets the user assign a custom key
sequence via ``QKeySequenceEdit``. Only sequences that differ from the
built-in default are persisted to ``prefs.shortcuts``; clearing a field
records an explicit "no shortcut" override, and matching the default
drops the override entirely.
"""
from __future__ import annotations

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.app_ui.preferences import Preferences


class ShortcutsDialog(QDialog):
    """Edit per-action keyboard shortcuts."""

    def __init__(self, prefs: Preferences, actions: dict, defaults: dict,
                 apply_fn, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(420, 520)
        self._prefs     = prefs
        self._defaults  = defaults          # {name: default key sequence str}
        self._apply_fn  = apply_fn          # callable() — rebuild menus
        self._editors: dict[str, QKeySequenceEdit] = {}

        root = QVBoxLayout(self)
        hint = QLabel(
            "Set a custom key for any command. Clear a field to remove its "
            "shortcut; matching the original restores the default."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(6)
        for name in sorted(actions):
            edit = QKeySequenceEdit(actions[name].shortcut())
            self._editors[name] = edit
            form.addRow(name, edit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        reset_row = QHBoxLayout()
        reset_btn = QPushButton("Reset All to Defaults")
        reset_btn.clicked.connect(self._reset_all)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch()
        root.addLayout(reset_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._commit)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _reset_all(self) -> None:
        for name, edit in self._editors.items():
            edit.setKeySequence(QKeySequence(self._defaults.get(name, "")))

    def _commit(self) -> None:
        overrides: dict[str, str] = {}
        for name, edit in self._editors.items():
            seq = edit.keySequence().toString()
            default = QKeySequence(self._defaults.get(name, "")).toString()
            if seq != default:
                overrides[name] = seq
        self._prefs.shortcuts = overrides
        self._prefs.save()
        self._apply_fn()
        self.accept()
