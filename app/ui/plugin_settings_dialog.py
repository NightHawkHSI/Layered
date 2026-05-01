"""Generic settings dialog built from a list of `Setting` specs."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..plugin_api import Setting


class PluginSettingsDialog(QDialog):
    def __init__(self, title: str, settings: list[Setting], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self._settings = settings
        self._widgets: dict[str, object] = {}
        self._color_state: dict[str, tuple[int, int, int, int]] = {}

        form = QFormLayout()
        for spec in settings:
            label = spec.label or spec.name
            widget = self._build_widget(spec)
            form.addRow(label + ":", widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if not settings:
            layout.addWidget(QLabel("This plugin has no configurable settings."))
        else:
            layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def _build_widget(self, spec: Setting) -> QWidget:
        t = spec.type
        if t == "int":
            w = QSpinBox()
            w.setRange(int(spec.min if spec.min is not None else -10**6),
                       int(spec.max if spec.max is not None else 10**6))
            if spec.step:
                w.setSingleStep(int(spec.step))
            w.setValue(int(spec.default or 0))
            self._widgets[spec.name] = w
            return w
        if t == "float":
            w = QDoubleSpinBox()
            w.setRange(float(spec.min if spec.min is not None else -1e9),
                       float(spec.max if spec.max is not None else 1e9))
            w.setDecimals(3)
            if spec.step:
                w.setSingleStep(float(spec.step))
            w.setValue(float(spec.default or 0.0))
            self._widgets[spec.name] = w
            return w
        if t == "bool":
            w = QCheckBox()
            w.setChecked(bool(spec.default))
            self._widgets[spec.name] = w
            return w
        if t == "choice":
            w = QComboBox()
            choices = spec.choices or []
            w.addItems(choices)
            if spec.default in choices:
                w.setCurrentText(str(spec.default))
            self._widgets[spec.name] = w
            return w
        if t == "string":
            w = QLineEdit(str(spec.default or ""))
            self._widgets[spec.name] = w
            return w
        if t == "color":
            default = spec.default or (255, 255, 255, 255)
            if len(default) == 3:
                default = (*default, 255)
            self._color_state[spec.name] = tuple(default)  # type: ignore
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            btn = QPushButton()
            btn.setStyleSheet(self._swatch(default))
            btn.setMinimumHeight(28)
            btn.clicked.connect(lambda _=False, s=spec, b=btn: self._pick_color(s, b))
            row.addWidget(btn, 1)
            self._widgets[spec.name] = btn
            return container

        # Fallback to read-only label.
        label = QLabel(repr(spec.default))
        self._widgets[spec.name] = label
        return label

    def _swatch(self, color) -> str:
        r, g, b, a = color
        return f"background: rgba({r},{g},{b},{a/255:.3f}); border: 1px solid #222;"

    def _pick_color(self, spec: Setting, btn: QPushButton) -> None:
        cur = self._color_state.get(spec.name, (255, 255, 255, 255))
        c = QColorDialog.getColor(
            QColor(*cur), self, spec.label or spec.name,
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if c.isValid():
            self._color_state[spec.name] = (c.red(), c.green(), c.blue(), c.alpha())
            btn.setStyleSheet(self._swatch(self._color_state[spec.name]))

    def values(self) -> dict:
        out: dict = {}
        for spec in self._settings:
            w = self._widgets.get(spec.name)
            if isinstance(w, QSpinBox):
                out[spec.name] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                out[spec.name] = w.value()
            elif isinstance(w, QCheckBox):
                out[spec.name] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[spec.name] = w.currentText()
            elif isinstance(w, QLineEdit):
                out[spec.name] = w.text()
            elif spec.type == "color":
                out[spec.name] = self._color_state.get(spec.name, spec.default)
            else:
                out[spec.name] = spec.default
        return out
