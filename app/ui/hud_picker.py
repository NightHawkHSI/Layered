"""Floating brush HUD: size, opacity, hardness, primary/secondary colors.

Toggle via Shift+S anywhere in the main window. Anchors at the cursor when
shown so the user keeps focus on the canvas instead of trekking to the
sidebars. Reads/writes the active Tool's instance attrs (brush_size /
brush_opacity / brush_hardness) and falls back to ToolContext for legacy
tools that still keep their settings on the shared context.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .slider_field import SliderField


def _swatch_qss(rgba: tuple[int, int, int, int]) -> str:
    r, g, b, a = rgba
    return (
        f"QPushButton {{ background: rgba({r},{g},{b},{a}); "
        f"border: 1px solid #555; border-radius: 4px; min-width: 28px; "
        f"min-height: 22px; }}"
    )


class HudPicker(QFrame):
    """Compact floating HUD with brush + color controls."""

    def __init__(self, host) -> None:
        super().__init__(host, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: rgba(36,38,42,235); "
            "border: 1px solid #3c3f44; border-radius: 8px; }"
            "QLabel { color: #dcdddd; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("Brush HUD")
        title.setStyleSheet("font-weight: 600;")
        root.addWidget(title)

        self._size = SliderField(1, 1024, 20, suffix=" px")
        self._size.valueChanged.connect(self._on_size)
        self._add_row(root, "Size", self._size)

        self._opacity = SliderField(1, 100, 100, suffix="%")
        self._opacity.valueChanged.connect(self._on_opacity)
        self._add_row(root, "Opacity", self._opacity)

        self._hardness = SliderField(0, 100, 80, suffix="%")
        self._hardness.valueChanged.connect(self._on_hardness)
        self._add_row(root, "Hardness", self._hardness)

        col_row = QHBoxLayout()
        col_row.setSpacing(6)
        col_row.addWidget(QLabel("Colors"))
        self._primary = QPushButton()
        self._primary.clicked.connect(self._pick_primary)
        col_row.addWidget(self._primary)
        self._secondary = QPushButton()
        self._secondary.clicked.connect(self._pick_secondary)
        col_row.addWidget(self._secondary)
        col_row.addStretch(1)
        root.addLayout(col_row)

        self.hide()

    @staticmethod
    def _add_row(parent_layout, label: str, widget: QWidget) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        lab = QLabel(label)
        lab.setMinimumWidth(60)
        row.addWidget(lab)
        row.addWidget(widget, 1)
        parent_layout.addLayout(row)

    def _active_tool(self):
        canvas = getattr(self._host, "canvas", None)
        return getattr(canvas, "tool", None) if canvas is not None else None

    def _ctx(self):
        return getattr(self._host, "tool_ctx", None)

    def _read(self, attr: str, default):
        tool = self._active_tool()
        if tool is not None and hasattr(tool, attr):
            return getattr(tool, attr)
        ctx = self._ctx()
        if ctx is not None and hasattr(ctx, attr):
            return getattr(ctx, attr)
        return default

    def _write(self, attr: str, value) -> None:
        tool = self._active_tool()
        if tool is not None and hasattr(tool, attr):
            setattr(tool, attr, value)
        ctx = self._ctx()
        if ctx is not None and hasattr(ctx, attr):
            setattr(ctx, attr, value)

    def _refresh_from_state(self) -> None:
        for sf, attr, scale, default in (
            (self._size,     "brush_size",     1,    20),
            (self._opacity,  "brush_opacity",  100,  1.0),
            (self._hardness, "brush_hardness", 100,  0.8),
        ):
            v = self._read(attr, default)
            sf.blockSignals(True)
            sf.setValue(int(v * scale))
            sf.blockSignals(False)

        ctx = self._ctx()
        if ctx is not None:
            self._primary.setStyleSheet(_swatch_qss(ctx.primary_color))
            self._secondary.setStyleSheet(_swatch_qss(ctx.secondary_color))

    def _on_size(self, v: int) -> None:
        self._write("brush_size", int(v))

    def _on_opacity(self, v: int) -> None:
        self._write("brush_opacity", v / 100.0)

    def _on_hardness(self, v: int) -> None:
        self._write("brush_hardness", v / 100.0)

    def _pick_primary(self) -> None:
        self._pick_color("primary_color", self._primary)

    def _pick_secondary(self) -> None:
        self._pick_color("secondary_color", self._secondary)

    def _pick_color(self, attr: str, btn: QPushButton) -> None:
        ctx = self._ctx()
        if ctx is None:
            return
        cur = getattr(ctx, attr)
        dlg = QColorDialog(QColor(*cur[:3]), self)
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        if dlg.exec():
            c = dlg.currentColor()
            new = (c.red(), c.green(), c.blue(), c.alpha())
            setattr(ctx, attr, new)
            btn.setStyleSheet(_swatch_qss(new))
            color_panel = getattr(self._host, "color_panel", None)
            if color_panel is not None and hasattr(color_panel, "refresh"):
                try:
                    color_panel.refresh()
                except Exception:
                    pass

    def toggle_at_cursor(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self._refresh_from_state()
        self.adjustSize()
        pos: QPoint = QCursor.pos()
        # Offset so the HUD doesn't sit directly under the pointer.
        self.move(pos.x() + 16, pos.y() + 16)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e) -> None:  # type: ignore[override]
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(e)
