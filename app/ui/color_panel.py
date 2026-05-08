"""Color panel: primary/secondary swatches, HSV color wheel, quick palette.

Left-click on the wheel or any palette swatch sets the **primary** color.
Right-click sets the **secondary** color.

Improvements over v1
--------------------
* ColorWheel rendered with QPainter gradients — O(1) vs O(n²) pixel loop.
* Crosshair indicators for both primary *and* secondary colors on the wheel.
* Hex input field for keyboard-precise color entry.
* Dedicated alpha slider (no need to open the full dialog just to adjust opacity).
* Recent-colors strip (last 10 unique picks, persisted per session).
* Cache key uses rounded int, eliminating float-equality fragility.
* NoPen set explicitly before every filled draw call.
"""
from __future__ import annotations

import colorsys
import math
from collections import deque
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegularExpressionValidator,
)
from PyQt6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..tools import ToolContext
from .slider_field import SliderField

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RGBA = tuple[int, int, int, int]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RECENT_MAX = 10

QUICK_COLORS: list[RGBA] = [
    (0,   0,   0,   255), (255, 255, 255, 255),
    (128, 128, 128, 255), (192, 192, 192, 255),
    (255,   0,   0,   255), (255, 128,   0, 255),
    (255, 255,   0,   255), (128, 255,   0, 255),
    (0,   255,   0,   255), (0,   255, 128, 255),
    (0,   255, 255,   255), (0,   128, 255, 255),
    (0,     0, 255,   255), (128,   0, 255, 255),
    (255,   0, 255,   255), (255,   0, 128, 255),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qcolor(c: RGBA) -> QColor:
    return QColor(c[0], c[1], c[2], c[3])


def _swatch_style(c: RGBA) -> str:
    r, g, b, a = c
    return (
        f"background: rgba({r},{g},{b},{a/255:.3f}); "
        "border: 1px solid #222; min-height: 40px;"
    )


def _to_rgba(color) -> RGBA:
    """Normalise a 3- or 4-tuple of ints to RGBA."""
    if len(color) == 3:
        return (int(color[0]), int(color[1]), int(color[2]), 255)
    return (int(color[0]), int(color[1]), int(color[2]), int(color[3]))


def _hsv_of(c: RGBA) -> tuple[float, float]:
    """Return (hue 0-360, sat 0-1) for a colour, ignoring value."""
    r, g, b, _ = c
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360.0, s


# ---------------------------------------------------------------------------
# ColorWheel
# ---------------------------------------------------------------------------

class ColorWheel(QWidget):
    """HSV colour wheel rendered with QPainter gradients (fast).

    * Hue  → angle around the ring
    * Saturation → distance from centre
    * Value (brightness) → controlled externally via :meth:`set_value`

    A small circle marks the *primary* colour position; a triangle marks the
    *secondary* colour position so both are visible simultaneously.
    """

    primary_picked   = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(80, 80)
        self._value: float = 1.0          # 0..1

        # Cache invalidation: (side_px, value_permille)
        self._cache: Optional[QPixmap] = None
        self._cache_key: tuple[int, int] = (-1, -1)

        # Indicator positions (hue°, sat 0-1); None = no indicator
        self._primary_hsv:   Optional[tuple[float, float]] = None
        self._secondary_hsv: Optional[tuple[float, float]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self._cache = None          # brightness changes the wheel appearance
        self.update()

    def set_primary_indicator(self, c: RGBA) -> None:
        self._primary_hsv = _hsv_of(c)
        self.update()

    def set_secondary_indicator(self, c: RGBA) -> None:
        self._secondary_hsv = _hsv_of(c)
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _build_cache(self, side: int) -> QPixmap:
        """Render the wheel using two gradient layers — O(1) complexity."""
        key = (side, round(self._value * 1000))
        if self._cache is not None and self._cache_key == key:
            return self._cache

        px = QPixmap(side, side)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        cx = cy = side / 2.0
        r  = side / 2.0
        centre = QPointF(cx, cy)

        # ── Layer 1: conical hue gradient (full saturation, current value) ──
        hue_grad = QConicalGradient(centre, 0.0)
        for i in range(361):
            # QConicalGradient sweeps CCW in screen coords (y-down), which
            # matches the standard colour-wheel convention.  Stop fraction
            # i/360 maps directly to hue i/360 — no reversal needed.
            hue_grad.setColorAt(
                i / 360.0,
                QColor.fromHsvF(i / 360.0, 1.0, self._value),
            )
        p.setBrush(QBrush(hue_grad))
        p.drawEllipse(centre, r, r)

        # ── Layer 2: radial gradient  (desaturates towards centre) ──
        # Centre colour = neutral grey at current value; edge = transparent.
        grey_val = int(self._value * 255)
        sat_grad = QRadialGradient(centre, r)
        sat_grad.setColorAt(0.0, QColor(grey_val, grey_val, grey_val, 255))
        sat_grad.setColorAt(1.0, QColor(grey_val, grey_val, grey_val,   0))
        p.setBrush(QBrush(sat_grad))
        p.drawEllipse(centre, r, r)

        p.end()
        self._cache     = px
        self._cache_key = key
        return px

    def paintEvent(self, _e: QPaintEvent) -> None:  # noqa: N802
        side = min(self.width(), self.height())
        if side <= 0:
            return

        x0 = (self.width()  - side) // 2
        y0 = (self.height() - side) // 2

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Wheel pixmap
        p.drawPixmap(QPoint(x0, y0), self._build_cache(side))

        # Outer ring
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(x0, y0, side, side)

        # Colour indicators
        r = side / 2.0
        cx = x0 + r
        cy = y0 + r

        if self._secondary_hsv is not None:
            self._draw_indicator(p, cx, cy, r, *self._secondary_hsv,
                                 shape="square", border=QColor(200, 200, 200))

        if self._primary_hsv is not None:
            self._draw_indicator(p, cx, cy, r, *self._primary_hsv,
                                 shape="circle", border=QColor(255, 255, 255))

    @staticmethod
    def _draw_indicator(
        p: QPainter,
        cx: float, cy: float, r: float,
        hue: float, sat: float,
        shape: str,
        border: QColor,
    ) -> None:
        angle_rad = math.radians(hue)
        ix = cx + math.cos(angle_rad) * sat * r
        iy = cy - math.sin(angle_rad) * sat * r   # negate: CCW matches gradient
        size = 7

        p.setPen(QPen(border, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if shape == "circle":
            p.drawEllipse(QPointF(ix, iy), size / 2, size / 2)
        else:
            p.drawRect(
                int(ix - size / 2), int(iy - size / 2),
                size, size,
            )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _color_at(self, pos: QPointF) -> Optional[RGBA]:
        side = min(self.width(), self.height())
        if side <= 0:
            return None
        x0 = (self.width()  - side) // 2
        y0 = (self.height() - side) // 2
        cx = x0 + side / 2.0
        cy = y0 + side / 2.0
        r  = side / 2.0
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.hypot(dx, dy)
        if dist > r:
            return None
        # Negate dy: QConicalGradient sweeps CCW in screen coords (y-down),
        # so we must measure angles CCW as well to keep hues aligned.
        hue = (math.degrees(math.atan2(-dy, dx)) + 360.0) % 360.0
        sat = min(1.0, dist / r)
        qc  = QColor.fromHsvF(hue / 360.0, sat, self._value)
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


# ---------------------------------------------------------------------------
# _Swatch
# ---------------------------------------------------------------------------

class _Swatch(QWidget):
    """Tiny colour swatch — LMB = primary, RMB = secondary."""

    primary_picked   = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, color: RGBA, size: int = 20,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)
        r, g, b = color[:3]
        self.setToolTip(f"#{r:02X}{g:02X}{b:02X}  (LMB=primary  RMB=secondary)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(self.rect(), _qcolor(self._color))
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.primary_picked.emit(self._color)
        elif e.button() == Qt.MouseButton.RightButton:
            self.secondary_picked.emit(self._color)


# ---------------------------------------------------------------------------
# _RecentColors
# ---------------------------------------------------------------------------

class _RecentColors(QWidget):
    """A single row of the last *N* unique colours picked."""

    primary_picked   = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, max_colors: int = _RECENT_MAX,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._max   = max_colors
        self._deque: deque[RGBA] = deque()
        self._row   = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(2)
        self._row.addStretch(1)

    def push(self, c: RGBA) -> None:
        """Add *c* to the front, removing duplicates and overflow."""
        if c in self._deque:
            self._deque.remove(c)
        self._deque.appendleft(c)
        if len(self._deque) > self._max:
            self._deque.pop()
        self._rebuild()

    def _rebuild(self) -> None:
        # Remove all swatch widgets (keep the trailing stretch)
        while self._row.count() > 1:
            item = self._row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for c in self._deque:
            sw = _Swatch(c, size=18)
            sw.primary_picked.connect(self.primary_picked)
            sw.secondary_picked.connect(self.secondary_picked)
            self._row.insertWidget(self._row.count() - 1, sw)


# ---------------------------------------------------------------------------
# ColorPanel
# ---------------------------------------------------------------------------

class ColorPanel(QWidget):
    primary_changed = pyqtSignal(tuple)

    def __init__(self, ctx: ToolContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.ctx = ctx

        # ── Primary / Secondary swatch buttons ──────────────────────────────
        self.primary_btn = QPushButton()
        self.primary_btn.setStyleSheet(_swatch_style(ctx.primary_color))
        self.primary_btn.clicked.connect(self._pick_primary)

        self.secondary_btn = QPushButton()
        self.secondary_btn.setStyleSheet(_swatch_style(ctx.secondary_color))
        self.secondary_btn.clicked.connect(self._pick_secondary)

        self.swap_btn = QPushButton("⇄ Swap")
        self.swap_btn.clicked.connect(self._swap)

        # ── Colour wheel ─────────────────────────────────────────────────────
        self.wheel = ColorWheel()
        self.wheel.primary_picked.connect(self.set_primary)
        self.wheel.secondary_picked.connect(self.set_secondary)
        self.wheel.set_primary_indicator(ctx.primary_color)
        self.wheel.set_secondary_indicator(ctx.secondary_color)

        # ── Value slider ─────────────────────────────────────────────────────
        self.value_slider = SliderField(0, 100, 100, suffix="%")
        self.value_slider.valueChanged.connect(
            lambda v: self.wheel.set_value(v / 100.0)
        )

        # ── Alpha slider ─────────────────────────────────────────────────────
        init_alpha = ctx.primary_color[3]
        self.alpha_slider = SliderField(0, 255, init_alpha, suffix="")
        self.alpha_slider.valueChanged.connect(self._alpha_changed)

        # ── Hex input ────────────────────────────────────────────────────────
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#RRGGBB or #RRGGBBAA")
        self.hex_edit.setMaxLength(9)
        hex_validator = QRegularExpressionValidator(
            __import__("PyQt6.QtCore", fromlist=["QRegularExpression"])
            .QRegularExpression(r"#?[0-9A-Fa-f]{0,8}")
        )
        self.hex_edit.setValidator(hex_validator)
        self.hex_edit.returnPressed.connect(self._apply_hex)
        self._update_hex_display(ctx.primary_color)

        # ── Recent colours ───────────────────────────────────────────────────
        self.recent = _RecentColors()
        self.recent.primary_picked.connect(self.set_primary)
        self.recent.secondary_picked.connect(self.set_secondary)

        # ── Layout ───────────────────────────────────────────────────────────
        inner = QWidget()
        inner.setMinimumSize(0, 0)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Colors  (LMB = primary · RMB = secondary)"))

        row = QHBoxLayout()
        row.addWidget(self.primary_btn, 1)
        row.addWidget(self.secondary_btn, 1)
        row.addWidget(self.swap_btn)
        lay.addLayout(row)

        lay.addWidget(self.wheel, 1)

        lay.addWidget(QLabel("Brightness"))
        lay.addWidget(self.value_slider)

        lay.addWidget(QLabel("Alpha"))
        lay.addWidget(self.alpha_slider)

        lay.addWidget(QLabel("Hex"))
        lay.addWidget(self.hex_edit)

        lay.addWidget(QLabel("Quick colors"))
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
        lay.addWidget(grid_host)

        lay.addWidget(QLabel("Recent"))
        lay.addWidget(self.recent)

        lay.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_primary(self, color) -> None:
        c = _to_rgba(color)
        self.ctx.primary_color = c
        self.primary_btn.setStyleSheet(_swatch_style(c))
        self.wheel.set_primary_indicator(c)
        self._update_hex_display(c)
        # Sync alpha slider without re-triggering set_primary
        self.alpha_slider.blockSignals(True)
        self.alpha_slider.setValue(c[3])
        self.alpha_slider.blockSignals(False)
        self.recent.push(c)
        self.primary_changed.emit(c)

    def set_secondary(self, color) -> None:
        c = _to_rgba(color)
        self.ctx.secondary_color = c
        self.secondary_btn.setStyleSheet(_swatch_style(c))
        self.wheel.set_secondary_indicator(c)
        self.recent.push(c)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _pick_primary(self) -> None:
        qc = QColorDialog.getColor(
            _qcolor(self.ctx.primary_color), self, "Primary color",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if qc.isValid():
            self.set_primary((qc.red(), qc.green(), qc.blue(), qc.alpha()))

    def _pick_secondary(self) -> None:
        qc = QColorDialog.getColor(
            _qcolor(self.ctx.secondary_color), self, "Secondary color",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if qc.isValid():
            self.set_secondary((qc.red(), qc.green(), qc.blue(), qc.alpha()))

    def _swap(self) -> None:
        p = self.ctx.primary_color
        s = self.ctx.secondary_color
        self.set_primary(s)
        self.set_secondary(p)

    def _alpha_changed(self, value: int) -> None:
        r, g, b, _ = self.ctx.primary_color
        self.set_primary((r, g, b, value))

    def _apply_hex(self) -> None:
        text = self.hex_edit.text().strip().lstrip("#")
        try:
            if len(text) == 6:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
                self.set_primary((r, g, b, self.ctx.primary_color[3]))
            elif len(text) == 8:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
                a = int(text[6:8], 16)
                self.set_primary((r, g, b, a))
        except ValueError:
            pass  # silently ignore invalid hex

    def _update_hex_display(self, c: RGBA) -> None:
        r, g, b, a = c
        text = f"#{r:02X}{g:02X}{b:02X}" if a == 255 else f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        # Only update if the user isn't currently editing
        if not self.hex_edit.hasFocus():
            self.hex_edit.setText(text)