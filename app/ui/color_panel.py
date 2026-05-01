"""Color panel: primary/secondary swatches with picker dialogs."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..tools import ToolContext


def _qcolor_from_tuple(c) -> QColor:
    r, g, b, a = c
    return QColor(r, g, b, a)


def _swatch_style(color) -> str:
    r, g, b, a = color
    return f"background: rgba({r},{g},{b},{a/255:.3f}); border: 1px solid #222; min-height: 40px;"


class ColorPanel(QWidget):
    primary_changed = pyqtSignal(tuple)

    def __init__(self, ctx: ToolContext, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.ctx = ctx

        self.primary_btn = QPushButton()
        self.primary_btn.setStyleSheet(_swatch_style(ctx.primary_color))
        self.primary_btn.clicked.connect(self._pick_primary)

        self.secondary_btn = QPushButton()
        self.secondary_btn.setStyleSheet(_swatch_style(ctx.secondary_color))
        self.secondary_btn.clicked.connect(self._pick_secondary)

        self.swap_btn = QPushButton("Swap")
        self.swap_btn.clicked.connect(self._swap)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Colors"))
        row = QHBoxLayout()
        row.addWidget(self.primary_btn)
        row.addWidget(self.secondary_btn)
        layout.addLayout(row)
        layout.addWidget(self.swap_btn)
        layout.addStretch(1)

    def set_primary(self, color) -> None:
        if isinstance(color, tuple) and len(color) == 3:
            color = (*color, 255)
        self.ctx.primary_color = tuple(int(c) for c in color)  # type: ignore
        self.primary_btn.setStyleSheet(_swatch_style(self.ctx.primary_color))
        self.primary_changed.emit(self.ctx.primary_color)

    def set_secondary(self, color) -> None:
        if isinstance(color, tuple) and len(color) == 3:
            color = (*color, 255)
        self.ctx.secondary_color = tuple(int(c) for c in color)  # type: ignore
        self.secondary_btn.setStyleSheet(_swatch_style(self.ctx.secondary_color))

    def _pick_primary(self) -> None:
        c = QColorDialog.getColor(_qcolor_from_tuple(self.ctx.primary_color), self, "Primary color",
                                  options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.set_primary((c.red(), c.green(), c.blue(), c.alpha()))

    def _pick_secondary(self) -> None:
        c = QColorDialog.getColor(_qcolor_from_tuple(self.ctx.secondary_color), self, "Secondary color",
                                  options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.set_secondary((c.red(), c.green(), c.blue(), c.alpha()))

    def _swap(self) -> None:
        p = self.ctx.primary_color
        s = self.ctx.secondary_color
        self.set_primary(s)
        self.set_secondary(p)
