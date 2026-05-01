"""Color panel: primary/secondary swatches, HSV color wheel, quick palette.

Left-click on the wheel or any palette swatch sets the **primary** color.
Right-click sets the **secondary** color.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
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


# 16 quick-pick colors.
QUICK_COLORS: list[tuple[int, int, int, int]] = [
    (0, 0, 0, 255), (255, 255, 255, 255),
    (128, 128, 128, 255), (192, 192, 192, 255),
    (255, 0, 0, 255), (255, 128, 0, 255),
    (255, 255, 0, 255), (128, 255, 0, 255),
    (0, 255, 0, 255), (0, 255, 128, 255),
    (0, 255, 255, 255), (0, 128, 255, 255),
    (0, 0, 255, 255), (128, 0, 255, 255),
    (255, 0, 255, 255), (255, 0, 128, 255),
]


class ColorWheel(QWidget):
    """HSV color wheel: hue around the ring, saturation along the radius.

    Value (brightness) controlled by an external slider via `set_value`.
    Left-click picks primary (`primary_picked`); right-click picks secondary.
    """
    primary_picked = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(60, 60)
        self._value: float = 1.0  # 0..1
        self._cache: Optional[QImage] = None
        self._cache_for: tuple[int, float] = (0, -1.0)

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self._cache = None
        self.update()

    # --- rendering ---

    def _build_cache(self) -> QImage:
        side = min(self.width(), self.height())
        key = (side, self._value)
        if self._cache is not None and self._cache_for == key:
            return self._cache
        img = QImage(side, side, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        cx = cy = side / 2.0
        r = side / 2.0
        v_int = int(self._value * 255)
        for y in range(side):
            for x in range(side):
                dx = x - cx
                dy = y - cy
                dist = math.hypot(dx, dy)
                if dist > r:
                    continue
                hue = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
                sat = min(1.0, dist / r)
                qc = QColor.fromHsvF(hue / 360.0, sat, self._value)
                qc.setAlpha(255)
                img.setPixelColor(x, y, qc)
        self._cache = img
        self._cache_for = key
        return img

    def paintEvent(self, _e: QPaintEvent) -> None:  # noqa: N802
        side = min(self.width(), self.height())
        if side <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x0 = (self.width() - side) // 2
        y0 = (self.height() - side) // 2
        p.drawImage(QPoint(x0, y0), self._build_cache())
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(x0, y0, side, side)

    # --- input ---

    def _color_at(self, pos: QPointF) -> Optional[tuple[int, int, int, int]]:
        side = min(self.width(), self.height())
        if side <= 0:
            return None
        x0 = (self.width() - side) // 2
        y0 = (self.height() - side) // 2
        cx = x0 + side / 2.0
        cy = y0 + side / 2.0
        r = side / 2.0
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.hypot(dx, dy)
        if dist > r:
            return None
        hue = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
        sat = min(1.0, dist / r)
        qc = QColor.fromHsvF(hue / 360.0, sat, self._value)
        return (qc.red(), qc.green(), qc.blue(), 255)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        c = self._color_at(e.position())
        if c is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.primary_picked.emit(c)
        elif e.button() == Qt.MouseButton.RightButton:
            self.secondary_picked.emit(c)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        c = self._color_at(e.position())
        if c is None:
            return
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.primary_picked.emit(c)
        elif e.buttons() & Qt.MouseButton.RightButton:
            self.secondary_picked.emit(c)


class _Swatch(QWidget):
    """Tiny color swatch that emits primary on LMB, secondary on RMB."""
    primary_picked = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, color: tuple[int, int, int, int], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(20, 20)
        self.setToolTip(f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}  (LMB=primary, RMB=secondary)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        r, g, b, a = self._color
        p.fillRect(self.rect(), QColor(r, g, b, a))
        p.setPen(QPen(QColor(0, 0, 0, 200), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.primary_picked.emit(self._color)
        elif e.button() == Qt.MouseButton.RightButton:
            self.secondary_picked.emit(self._color)


class ColorPanel(QWidget):
    primary_changed = pyqtSignal(tuple)

    def __init__(self, ctx: ToolContext, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.ctx = ctx

        self.primary_btn = QPushButton()
        self.primary_btn.setStyleSheet(_swatch_style(ctx.primary_color))
        self.primary_btn.clicked.connect(self._pick_primary)

        self.secondary_btn = QPushButton()
        self.secondary_btn.setStyleSheet(_swatch_style(ctx.secondary_color))
        self.secondary_btn.clicked.connect(self._pick_secondary)

        self.swap_btn = QPushButton("Swap")
        self.swap_btn.clicked.connect(self._swap)

        self.wheel = ColorWheel()
        self.wheel.primary_picked.connect(self.set_primary)
        self.wheel.secondary_picked.connect(self.set_secondary)

        self.value_slider = QSlider(Qt.Orientation.Horizontal)
        self.value_slider.setRange(0, 100)
        self.value_slider.setValue(100)
        self.value_slider.valueChanged.connect(lambda v: self.wheel.set_value(v / 100.0))

        # All controls live in an inner widget so a QScrollArea can host
        # them — when the dock is shorter than the natural content height,
        # the panel scrolls instead of letting the quick-color swatches
        # overflow into the dock below.
        inner = QWidget()
        inner.setMinimumSize(0, 0)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Colors  (LMB=primary, RMB=secondary)"))
        row = QHBoxLayout()
        row.addWidget(self.primary_btn)
        row.addWidget(self.secondary_btn)
        layout.addLayout(row)
        layout.addWidget(self.swap_btn)

        layout.addWidget(self.wheel, 1)
        layout.addWidget(QLabel("Value"))
        layout.addWidget(self.value_slider)

        # Quick palette grid.
        layout.addWidget(QLabel("Quick colors"))
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        cols = 8
        for i, c in enumerate(QUICK_COLORS):
            sw = _Swatch(c)
            sw.primary_picked.connect(self.set_primary)
            sw.secondary_picked.connect(self.set_secondary)
            grid.addWidget(sw, i // cols, i % cols)
        layout.addWidget(grid_host)
        layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # --- public API ---

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
