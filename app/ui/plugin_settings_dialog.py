"""Generic settings dialog built from a list of `Setting` specs."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QTimer
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
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..plugin_api import Setting


class PluginSettingsDialog(QDialog):
    """Settings dialog with optional live preview.

    `preview_callback(values)` is called (debounced) whenever any setting
    changes, so the host can re-run the filter and show the result on the
    canvas before the user commits.
    """

    def __init__(
        self,
        title: str,
        settings: list[Setting],
        parent: Optional[QWidget] = None,
        preview_callback: Optional[Callable[[dict], None]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self._settings = settings
        self._widgets: dict[str, object] = {}
        self._color_state: dict[str, tuple[int, int, int, int]] = {}
        self._preview_callback = preview_callback

        # Debounce: filters can be expensive, so wait until the user pauses
        # adjusting before re-running. 80ms keeps it feeling immediate while
        # coalescing rapid drags.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(80)
        self._preview_timer.timeout.connect(self._fire_preview)

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

        if preview_callback is not None:
            self._wire_preview_signals()
            # Fire once after construction so the canvas immediately shows
            # the default-parameter filter result.
            QTimer.singleShot(0, self._fire_preview)

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
        if t == "text":
            w = QPlainTextEdit(str(spec.default or ""))
            w.setMinimumHeight(180)
            try:
                from PyQt6.QtGui import QFont
                mono = QFont("Consolas")
                mono.setStyleHint(QFont.StyleHint.Monospace)
                w.setFont(mono)
            except Exception:
                pass
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
            self._schedule_preview()

    def _wire_preview_signals(self) -> None:
        for spec in self._settings:
            w = self._widgets.get(spec.name)
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.valueChanged.connect(self._schedule_preview)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._schedule_preview)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._schedule_preview)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._schedule_preview)
            elif isinstance(w, QPlainTextEdit):
                w.textChanged.connect(self._schedule_preview)
            elif spec.type == "color":
                # Color picker fires through _pick_color — schedule there.
                pass

    def _schedule_preview(self, *_) -> None:
        self._preview_timer.start()

    def _fire_preview(self) -> None:
        if self._preview_callback is None:
            return
        try:
            self._preview_callback(self.values())
        except Exception:
            # Preview errors shouldn't kill the dialog — user can still
            # commit and let the host's normal error path surface it.
            pass

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
            elif isinstance(w, QPlainTextEdit):
                out[spec.name] = w.toPlainText()
            elif spec.type == "color":
                out[spec.name] = self._color_state.get(spec.name, spec.default)
            else:
                out[spec.name] = spec.default
        return out
