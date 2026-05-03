"""Slider paired with an editable numeric field.

Wraps QSlider + QSpinBox so users can either drag or type the value. The
two stay in sync; external code connects to `valueChanged` and uses
`value()` / `setValue()` exactly like a plain QSlider.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QSlider, QSpinBox, QWidget


class SliderField(QWidget):
    """Horizontal slider + spinbox with shared int value."""

    valueChanged = pyqtSignal(int)

    def __init__(
        self,
        lo: int,
        hi: int,
        init: int,
        suffix: str = "",
        slider_width: int | None = None,
        spin_width: int = 56,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(init)
        if slider_width is not None:
            self.slider.setFixedWidth(slider_width)

        self.spin = QSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setValue(init)
        if suffix:
            self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(spin_width)
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin, 0)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, v: int) -> None:
        if self.spin.value() != v:
            self.spin.blockSignals(True)
            self.spin.setValue(v)
            self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_spin(self, v: int) -> None:
        if self.slider.value() != v:
            self.slider.blockSignals(True)
            self.slider.setValue(v)
            self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, v: int) -> None:  # noqa: N802 — Qt convention
        self.slider.setValue(v)

    def setRange(self, lo: int, hi: int) -> None:  # noqa: N802
        self.slider.setRange(lo, hi)
        self.spin.setRange(lo, hi)

    def maximum(self) -> int:
        return self.slider.maximum()

    def minimum(self) -> int:
        return self.slider.minimum()

    def blockSignals(self, b: bool) -> bool:  # noqa: N802
        # Block both children so external batch-updates don't fire spurious
        # signals from either widget.
        self.spin.blockSignals(b)
        return self.slider.blockSignals(b)
