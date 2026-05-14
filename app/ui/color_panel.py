"""Color panel: primary/secondary swatches, HSV color wheel, quick palette.

Left-click on the wheel or any palette swatch sets the **primary** color.
Right-click sets the **secondary** color.

Improvements over v2
--------------------
* GradientSlider — fully custom slider widget with a painted gradient track
  so you see the *live effect* of dragging before you let go.
* Per-channel RGB sliders whose gradient tracks update dynamically (e.g. the
  Red slider always shows the ramp from (0, cur_G, cur_B) → (255, cur_G, cur_B)).
* Alpha slider rendered over a checkerboard so transparency is immediately
  obvious.
* Brightness slider track shows black → the current hue/sat at full value.
* HSV readout label under the wheel: "H: 230°  S: 85%  V: 92%".
* Live hex editing — colour updates on every valid 6/8-char keystroke, not
  only on Enter.  Also accepts lowercase and leading '#'.
* Copy-hex button — one click puts the current hex on the clipboard.
* Colour harmony strip — Complementary, Triadic, and Analogous swatches
  derived from the current primary, all LMB/RMB assignable.
* Section separators give the panel a clear visual hierarchy.
* blockSignals used correctly throughout to prevent feedback loops.
"""
from __future__ import annotations

import colorsys
import math
from collections import deque
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QClipboard,
    QColor,
    QConicalGradient,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegularExpressionValidator,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.plugins.tools import ToolContext

# ---------------------------------------------------------------------------
# Types & constants
# ---------------------------------------------------------------------------

RGBA = tuple[int, int, int, int]

_RECENT_MAX = 12

QUICK_COLORS: list[RGBA] = [
    (0,   0,   0,   255), (255, 255, 255, 255),
    (64,  64,  64,  255), (128, 128, 128, 255),
    (192, 192, 192, 255), (224, 224, 224, 255),
    (255,   0,   0,   255), (192,   0,   0, 255),
    (255, 128,   0, 255), (255, 192,   0, 255),
    (255, 255,   0,   255), (192, 255,   0, 255),
    (0,   255,   0,   255), (0,   192,   0, 255),
    (0,   255, 128, 255),  (0,   255, 255, 255),
    (0,   128, 255,   255), (0,     0, 255, 255),
    (128,   0, 255, 255),  (255,   0, 255, 255),
]

# ---------------------------------------------------------------------------
# Painting helpers
# ---------------------------------------------------------------------------

def _qcolor(c: RGBA) -> QColor:
    return QColor(c[0], c[1], c[2], c[3])


def _swatch_style(c: RGBA) -> str:
    r, g, b, a = c
    return (
        f"background: rgba({r},{g},{b},{a / 255:.3f}); "
        "border: 1px solid #222; min-height: 38px;"
    )


def _to_rgba(color) -> RGBA:
    if len(color) == 3:
        return (int(color[0]), int(color[1]), int(color[2]), 255)
    return (int(color[0]), int(color[1]), int(color[2]), int(color[3]))


def _hsv_of(c: RGBA) -> tuple[float, float]:
    """Return (hue 0-360, sat 0-1) ignoring value — used for wheel indicators."""
    r, g, b, _ = c
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360.0, s


def _draw_checkerboard(painter: QPainter, rect: QRect, cell: int = 5) -> None:
    """Fill *rect* with a two-tone grey checkerboard."""
    light = QColor(210, 210, 210)
    dark  = QColor(160, 160, 160)
    painter.save()
    painter.setClipRect(rect)
    painter.setPen(Qt.PenStyle.NoPen)
    col_y = 0
    y = rect.top()
    while y < rect.bottom() + 1:
        col_x = col_y
        x = rect.left()
        while x < rect.right() + 1:
            painter.setBrush(light if col_x % 2 == 0 else dark)
            painter.drawRect(x, y, cell, cell)
            col_x += 1
            x += cell
        col_y += 1
        y += cell
    painter.restore()


def _section_label(text: str) -> QLabel:
    """Create a small all-caps section header label."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "color: #888; font-size: 9px; font-weight: bold; "
        "letter-spacing: 1px; margin-top: 4px;"
    )
    return lbl


def _hsep() -> QFrame:
    """Thin horizontal separator line."""
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setStyleSheet("color: #333;")
    f.setFixedHeight(1)
    return f


# ---------------------------------------------------------------------------
# Colour math helpers
# ---------------------------------------------------------------------------

def _harmony_colors(c: RGBA) -> list[tuple[str, RGBA]]:
    """Return a flat list of (label, RGBA) harmony swatches for *c*."""
    r, g, b, a = c
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hue_deg = h * 360.0
    # Preserve reasonable saturation/value even on near-grey colours
    s = max(s, 0.65)
    v = max(v, 0.75)

    def at(deg: float) -> RGBA:
        hh = ((deg % 360.0) / 360.0) % 1.0
        rr, gg, bb = colorsys.hsv_to_rgb(hh, s, v)
        return (int(rr * 255), int(gg * 255), int(bb * 255), a)

    return [
        ("Comp",       at(hue_deg + 180)),
        ("Split –",    at(hue_deg + 150)),
        ("Split +",    at(hue_deg - 150)),
        ("Tri –",      at(hue_deg + 120)),
        ("Tri +",      at(hue_deg - 120)),
        ("Ana –",      at(hue_deg +  30)),
        ("Ana +",      at(hue_deg -  30)),
    ]


# ---------------------------------------------------------------------------
# GradientSlider
# ---------------------------------------------------------------------------

class GradientSlider(QWidget):
    """Horizontal slider with a painted gradient track.

    Gradient stops are set via :meth:`set_stops` or the convenience
    :meth:`set_two_color`.  Pass ``checkerboard=True`` to draw a grey
    checker *under* the gradient track (useful for alpha sliders).

    Supports mouse-wheel fine-tuning (±1 step per notch).
    """

    valueChanged = pyqtSignal(int)

    _HR   = 7    # handle radius, px
    _TH   = 11   # track height, px
    _HPAD = 10   # horizontal padding (keeps handle inside widget bounds)

    def __init__(self, min_val: int, max_val: int, value: int,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min     = min_val
        self._max     = max_val
        self._value   = max(min_val, min(max_val, value))
        self._stops:  list[tuple[float, QColor]] = [
            (0.0, QColor(0, 0, 0)), (1.0, QColor(255, 255, 255)),
        ]
        self._checker = False
        self.setFixedHeight(26)
        self.setMinimumWidth(50)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # ── Public API ────────────────────────────────────────────────────────

    def setValue(self, v: int) -> None:
        v = max(self._min, min(self._max, v))
        if v != self._value:
            self._value = v
            self.update()
            if not self.signalsBlocked():
                self.valueChanged.emit(v)

    def value(self) -> int:
        return self._value

    def set_stops(self, stops: list[tuple[float, QColor]],
                  checkerboard: bool = False) -> None:
        self._stops   = stops
        self._checker = checkerboard
        self.update()

    def set_two_color(self, c0: QColor, c1: QColor,
                      checkerboard: bool = False) -> None:
        self.set_stops([(0.0, c0), (1.0, c1)], checkerboard)

    # ── Geometry helpers ──────────────────────────────────────────────────

    def _track_rect(self) -> QRect:
        h = self._TH
        y = (self.height() - h) // 2
        return QRect(self._HPAD, y,
                     self.width() - 2 * self._HPAD, h)

    def _value_to_x(self, v: int) -> float:
        tr = self._track_rect()
        t  = (v - self._min) / max(1, self._max - self._min)
        return tr.left() + t * tr.width()

    def _x_to_value(self, x: float) -> int:
        tr = self._track_rect()
        t  = (x - tr.left()) / max(1, tr.width())
        t  = max(0.0, min(1.0, t))
        return int(round(self._min + t * (self._max - self._min)))

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, _e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track_rect()
        ftr = QRectF(tr)

        # Optional checker background
        if self._checker:
            _draw_checkerboard(p, tr, cell=5)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(30, 30, 30)))
            p.drawRoundedRect(ftr, 3, 3)

        # Gradient fill
        if len(self._stops) >= 2:
            grad = QLinearGradient(ftr.left(), 0, ftr.right(), 0)
            for pos, col in self._stops:
                grad.setColorAt(pos, col)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(ftr, 3, 3)

        # Track border
        p.setPen(QPen(QColor(0, 0, 0, 130), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(ftr, 3, 3)

        # Handle  — white circle with dark outline
        hx = self._value_to_x(self._value)
        hy = self.height() / 2.0
        p.setPen(QPen(QColor(20, 20, 20), 1.5))
        p.setBrush(QBrush(QColor(255, 255, 255, 230)))
        p.drawEllipse(QPointF(hx, hy), self._HR, self._HR)

    # ── Input ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            v = self._x_to_value(e.position().x())
            self._value = v
            self.update()
            if not self.signalsBlocked():
                self.valueChanged.emit(v)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            v = self._x_to_value(e.position().x())
            self._value = v
            self.update()
            if not self.signalsBlocked():
                self.valueChanged.emit(v)

    def wheelEvent(self, e: QWheelEvent) -> None:
        delta = 1 if e.angleDelta().y() > 0 else -1
        self.setValue(self._value + delta)
        e.accept()


# ---------------------------------------------------------------------------
# ColorWheel
# ---------------------------------------------------------------------------

class ColorWheel(QWidget):
    """HSV colour wheel rendered with QPainter gradients (fast, O(1)).

    * Hue  → angle around the ring
    * Saturation → distance from centre
    * Value (brightness) → set externally via :meth:`set_value`

    Primary colour position is marked by a circle; secondary by a square.
    """

    primary_picked   = pyqtSignal(tuple)
    secondary_picked = pyqtSignal(tuple)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(80, 80)
        self._value: float = 1.0

        self._cache:     Optional[QPixmap]       = None
        self._cache_key: tuple[int, int]         = (-1, -1)
        self._primary_hsv:   Optional[tuple[float, float]] = None
        self._secondary_hsv: Optional[tuple[float, float]] = None

    # ── Public API ────────────────────────────────────────────────────────

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self._cache = None
        self.update()

    def set_primary_indicator(self, c: RGBA) -> None:
        self._primary_hsv = _hsv_of(c)
        self.update()

    def set_secondary_indicator(self, c: RGBA) -> None:
        self._secondary_hsv = _hsv_of(c)
        self.update()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _build_cache(self, side: int) -> QPixmap:
        key = (side, round(self._value * 1000))
        if self._cache is not None and self._cache_key == key:
            return self._cache

        px = QPixmap(side, side)
        px.fill(Qt.GlobalColor.transparent)
        p  = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        cx = cy = side / 2.0
        r  = side / 2.0
        centre = QPointF(cx, cy)

        # Layer 1: conical hue gradient
        hue_grad = QConicalGradient(centre, 0.0)
        for i in range(361):
            hue_grad.setColorAt(i / 360.0,
                                QColor.fromHsvF(i / 360.0, 1.0, self._value))
        p.setBrush(QBrush(hue_grad))
        p.drawEllipse(centre, r, r)

        # Layer 2: radial white-out (desaturates towards centre)
        grey_val = int(self._value * 255)
        sat_grad = QRadialGradient(centre, r)
        sat_grad.setColorAt(0.0, QColor(grey_val, grey_val, grey_val, 255))
        sat_grad.setColorAt(1.0, QColor(grey_val, grey_val, grey_val,   0))
        p.setBrush(QBrush(sat_grad))
        p.drawEllipse(centre, r, r)

        p.end()
        self._cache, self._cache_key = px, key
        return px

    def paintEvent(self, _e: QPaintEvent) -> None:
        side = min(self.width(), self.height())
        if side <= 0:
            return
        x0 = (self.width()  - side) // 2
        y0 = (self.height() - side) // 2

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(QPoint(x0, y0), self._build_cache(side))

        # Outer border ring
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(x0, y0, side, side)

        r  = side / 2.0
        cx = x0 + r
        cy = y0 + r

        if self._secondary_hsv is not None:
            self._draw_indicator(p, cx, cy, r, *self._secondary_hsv,
                                 shape="square", border=QColor(200, 200, 200))
        if self._primary_hsv is not None:
            self._draw_indicator(p, cx, cy, r, *self._primary_hsv,
                                 shape="circle", border=QColor(255, 255, 255))

    @staticmethod
    def _draw_indicator(p: QPainter,
                        cx: float, cy: float, r: float,
                        hue: float, sat: float,
                        shape: str, border: QColor) -> None:
        angle_rad = math.radians(hue)
        ix = cx + math.cos(angle_rad) * sat * r
        iy = cy - math.sin(angle_rad) * sat * r
        sz = 7

        # Dark shadow for contrast on any background colour
        p.setPen(QPen(QColor(0, 0, 0, 160), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if shape == "circle":
            p.drawEllipse(QPointF(ix, iy), sz / 2, sz / 2)
        else:
            p.drawRect(int(ix - sz / 2), int(iy - sz / 2), sz, sz)

        p.setPen(QPen(border, 1.5))
        if shape == "circle":
            p.drawEllipse(QPointF(ix, iy), sz / 2, sz / 2)
        else:
            p.drawRect(int(ix - sz / 2), int(iy - sz / 2), sz, sz)

    # ── Input ─────────────────────────────────────────────────────────────

    def _color_at(self, pos: QPointF) -> Optional[RGBA]:
        side = min(self.width(), self.height())
        if side <= 0:
            return None
        x0 = (self.width()  - side) // 2
        y0 = (self.height() - side) // 2
        cx = x0 + side / 2.0
        cy = y0 + side / 2.0
        r  = side / 2.0
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.hypot(dx, dy)
        if dist > r:
            return None
        hue = (math.degrees(math.atan2(-dy, dx)) + 360.0) % 360.0
        sat = min(1.0, dist / r)
        qc  = QColor.fromHsvF(hue / 360.0, sat, self._value)
        return (qc.red(), qc.green(), qc.blue(), 255)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        c = self._color_at(e.position())
        if c is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.primary_picked.emit(c)
        elif e.button() == Qt.MouseButton.RightButton:
            self.secondary_picked.emit(c)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
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
                 tooltip: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)
        r, g, b = color[:3]
        tip = tooltip or f"#{r:02X}{g:02X}{b:02X}  (LMB=primary · RMB=secondary)"
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_color(self, color: RGBA) -> None:
        self._color = color
        r, g, b = color[:3]
        self.setToolTip(f"#{r:02X}{g:02X}{b:02X}  (LMB=primary · RMB=secondary)")
        self.update()

    def paintEvent(self, _e: QPaintEvent) -> None:
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        # Checker background (visible for semi-transparent swatches)
        _draw_checkerboard(p, self.rect(), cell=4)
        p.fillRect(self.rect(), _qcolor(self._color))
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.primary_picked.emit(self._color)
        elif e.button() == Qt.MouseButton.RightButton:
            self.secondary_picked.emit(self._color)


# ---------------------------------------------------------------------------
# _RecentColors
# ---------------------------------------------------------------------------

class _RecentColors(QWidget):
    """A single scrollable row of the last N unique colours picked."""

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
        if c in self._deque:
            self._deque.remove(c)
        self._deque.appendleft(c)
        if len(self._deque) > self._max:
            self._deque.pop()
        self._rebuild()

    def _rebuild(self) -> None:
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

    def __init__(self, ctx: ToolContext,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.ctx = ctx

        # ── Primary / Secondary swatches ─────────────────────────────────
        self.primary_btn = QPushButton()
        self.primary_btn.setStyleSheet(_swatch_style(ctx.primary_color))
        self.primary_btn.setToolTip("Click to open colour dialog")
        self.primary_btn.clicked.connect(self._pick_primary)

        self.secondary_btn = QPushButton()
        self.secondary_btn.setStyleSheet(_swatch_style(ctx.secondary_color))
        self.secondary_btn.setToolTip("Click to open colour dialog")
        self.secondary_btn.clicked.connect(self._pick_secondary)

        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setFixedWidth(32)
        self.swap_btn.setToolTip("Swap primary ↔ secondary")
        self.swap_btn.clicked.connect(self._swap)

        # ── Colour wheel ──────────────────────────────────────────────────
        self.wheel = ColorWheel()
        self.wheel.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        self.wheel.primary_picked.connect(self.set_primary)
        self.wheel.secondary_picked.connect(self.set_secondary)
        self.wheel.set_primary_indicator(ctx.primary_color)
        self.wheel.set_secondary_indicator(ctx.secondary_color)

        # ── HSV readout ───────────────────────────────────────────────────
        self._hsv_label = QLabel()
        self._hsv_label.setStyleSheet(
            "color: #aaa; font-size: 10px; font-family: monospace;"
        )
        self._hsv_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_hsv_label(ctx.primary_color)

        # ── Brightness (wheel value) slider ───────────────────────────────
        r0, g0, b0, _ = ctx.primary_color
        self.bright_slider = GradientSlider(0, 100, 100)
        self._update_bright_gradient(ctx.primary_color)
        self.bright_slider.valueChanged.connect(
            lambda v: self.wheel.set_value(v / 100.0)
        )

        # ── RGB channel sliders ───────────────────────────────────────────
        r0, g0, b0, _ = ctx.primary_color
        self._r_slider = GradientSlider(0, 255, r0)
        self._g_slider = GradientSlider(0, 255, g0)
        self._b_slider = GradientSlider(0, 255, b0)

        self._update_rgb_gradients(ctx.primary_color)

        self._r_slider.valueChanged.connect(self._on_rgb_changed)
        self._g_slider.valueChanged.connect(self._on_rgb_changed)
        self._b_slider.valueChanged.connect(self._on_rgb_changed)

        # ── Alpha slider ──────────────────────────────────────────────────
        self._alpha_slider = GradientSlider(0, 255, ctx.primary_color[3])
        self._update_alpha_gradient(ctx.primary_color)
        self._alpha_slider.valueChanged.connect(self._on_alpha_changed)

        # ── Hex input + copy button ───────────────────────────────────────
        self._hex_edit = QLineEdit()
        self._hex_edit.setPlaceholderText("#RRGGBB")
        self._hex_edit.setMaxLength(9)
        self._hex_edit.setFixedWidth(80)
        hex_re = __import__("PyQt6.QtCore", fromlist=["QRegularExpression"]) \
                     .QRegularExpression(r"#?[0-9A-Fa-f]{0,8}")
        self._hex_edit.setValidator(QRegularExpressionValidator(hex_re))
        self._hex_edit.textEdited.connect(self._on_hex_edited)
        self._update_hex_display(ctx.primary_color)

        copy_btn = QPushButton("⎘")
        copy_btn.setFixedWidth(28)
        copy_btn.setToolTip("Copy hex to clipboard")
        copy_btn.clicked.connect(self._copy_hex)

        # ── Colour harmony swatches ───────────────────────────────────────
        # Pre-create 7 swatches; recolour them in _update_harmony()
        self._harmony_swatches: list[tuple[str, _Swatch]] = []
        self._harmony_row = QHBoxLayout()
        self._harmony_row.setContentsMargins(0, 0, 0, 0)
        self._harmony_row.setSpacing(3)
        for label, hc in _harmony_colors(ctx.primary_color):
            sw = _Swatch(hc, size=20, tooltip=label)
            sw.primary_picked.connect(self.set_primary)
            sw.secondary_picked.connect(self.set_secondary)
            col_lbl = QLabel(label.split()[0])
            col_lbl.setStyleSheet("color: #777; font-size: 8px;")
            col_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cell = QVBoxLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setSpacing(1)
            cell.addWidget(sw, alignment=Qt.AlignmentFlag.AlignHCenter)
            cell.addWidget(col_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._harmony_swatches.append((label, sw))
            self._harmony_row.addLayout(cell)
        self._harmony_row.addStretch(1)

        # ── Quick palette ─────────────────────────────────────────────────
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        cols = 10
        for i, c in enumerate(QUICK_COLORS):
            sw = _Swatch(c, size=18)
            sw.primary_picked.connect(self.set_primary)
            sw.secondary_picked.connect(self.set_secondary)
            grid.addWidget(sw, i // cols, i % cols)

        # ── Recent colours ────────────────────────────────────────────────
        self.recent = _RecentColors()
        self.recent.primary_picked.connect(self.set_primary)
        self.recent.secondary_picked.connect(self.set_secondary)

        # ── Layout ────────────────────────────────────────────────────────
        inner = QWidget()
        inner.setMinimumSize(0, 0)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)

        # Swatches row
        lay.addWidget(_section_label("Colours  (LMB = primary · RMB = secondary)"))
        swatch_row = QHBoxLayout()
        swatch_row.addWidget(self.primary_btn, 1)
        swatch_row.addWidget(self.swap_btn)
        swatch_row.addWidget(self.secondary_btn, 1)
        lay.addLayout(swatch_row)

        # Wheel
        lay.addWidget(_hsep())
        lay.addWidget(self.wheel, 1)
        lay.addWidget(self._hsv_label)

        # Brightness
        lay.addWidget(_section_label("Brightness (wheel)"))
        lay.addWidget(self.bright_slider)

        # RGB
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("RGB"))
        rgb_grid = QGridLayout()
        rgb_grid.setContentsMargins(0, 0, 0, 0)
        rgb_grid.setHorizontalSpacing(4)
        rgb_grid.setVerticalSpacing(2)
        for row_i, (letter, slider) in enumerate([
            ("R", self._r_slider),
            ("G", self._g_slider),
            ("B", self._b_slider),
        ]):
            lbl = QLabel(letter)
            lbl.setFixedWidth(10)
            lbl.setStyleSheet("color: #bbb; font-size: 10px;")
            rgb_grid.addWidget(lbl, row_i, 0)
            rgb_grid.addWidget(slider, row_i, 1)
        lay.addLayout(rgb_grid)

        # Alpha
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("Alpha"))
        lay.addWidget(self._alpha_slider)

        # Hex
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("Hex"))
        hex_row = QHBoxLayout()
        hex_row.setContentsMargins(0, 0, 0, 0)
        hex_row.addWidget(self._hex_edit)
        hex_row.addWidget(copy_btn)
        hex_row.addStretch(1)
        lay.addLayout(hex_row)

        # Harmony
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("Harmony"))
        lay.addLayout(self._harmony_row)

        # Quick colours
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("Quick"))
        lay.addWidget(grid_host)

        # Recent
        lay.addWidget(_hsep())
        lay.addWidget(_section_label("Recent"))
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
        self._update_hsv_label(c)
        self._update_rgb_sliders(c)
        self._update_rgb_gradients(c)
        self._update_alpha_gradient(c)
        self._update_bright_gradient(c)
        self._update_harmony(c)
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
            _qcolor(self.ctx.primary_color), self, "Primary colour",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if qc.isValid():
            self.set_primary((qc.red(), qc.green(), qc.blue(), qc.alpha()))

    def _pick_secondary(self) -> None:
        qc = QColorDialog.getColor(
            _qcolor(self.ctx.secondary_color), self, "Secondary colour",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if qc.isValid():
            self.set_secondary((qc.red(), qc.green(), qc.blue(), qc.alpha()))

    def _swap(self) -> None:
        p, s = self.ctx.primary_color, self.ctx.secondary_color
        self.set_primary(s)
        self.set_secondary(p)

    def _on_rgb_changed(self, _unused: int) -> None:
        r = self._r_slider.value()
        g = self._g_slider.value()
        b = self._b_slider.value()
        a = self.ctx.primary_color[3]
        self.set_primary((r, g, b, a))

    def _on_alpha_changed(self, value: int) -> None:
        r, g, b, _ = self.ctx.primary_color
        self.set_primary((r, g, b, value))

    def _on_hex_edited(self, text: str) -> None:
        cleaned = text.strip().lstrip("#")
        try:
            if len(cleaned) == 6:
                r = int(cleaned[0:2], 16)
                g = int(cleaned[2:4], 16)
                b = int(cleaned[4:6], 16)
                self.set_primary((r, g, b, self.ctx.primary_color[3]))
            elif len(cleaned) == 8:
                r = int(cleaned[0:2], 16)
                g = int(cleaned[2:4], 16)
                b = int(cleaned[4:6], 16)
                a = int(cleaned[6:8], 16)
                self.set_primary((r, g, b, a))
        except ValueError:
            pass  # Partial entry — ignore until complete

    def _copy_hex(self) -> None:
        r, g, b, a = self.ctx.primary_color
        text = f"#{r:02X}{g:02X}{b:02X}" if a == 255 else f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        QApplication.clipboard().setText(text)

    # ------------------------------------------------------------------
    # Update helpers (called from set_primary to keep widgets in sync)
    # ------------------------------------------------------------------

    def _update_hex_display(self, c: RGBA) -> None:
        if not self._hex_edit.hasFocus():
            r, g, b, a = c
            t = f"#{r:02X}{g:02X}{b:02X}" if a == 255 else f"#{r:02X}{g:02X}{b:02X}{a:02X}"
            self._hex_edit.setText(t)

    def _update_hsv_label(self, c: RGBA) -> None:
        r, g, b, _ = c
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._hsv_label.setText(
            f"H: {h * 360:.0f}°   S: {s * 100:.0f}%   V: {v * 100:.0f}%"
        )

    def _update_rgb_sliders(self, c: RGBA) -> None:
        r, g, b, a = c
        for slider, val in ((self._r_slider, r),
                            (self._g_slider, g),
                            (self._b_slider, b),
                            (self._alpha_slider, a)):
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)

    def _update_rgb_gradients(self, c: RGBA) -> None:
        r, g, b, _ = c
        self._r_slider.set_two_color(QColor(0, g, b), QColor(255, g, b))
        self._g_slider.set_two_color(QColor(r, 0, b), QColor(r, 255, b))
        self._b_slider.set_two_color(QColor(r, g, 0), QColor(r, g, 255))

    def _update_alpha_gradient(self, c: RGBA) -> None:
        r, g, b, _ = c
        self._alpha_slider.set_two_color(
            QColor(r, g, b, 0), QColor(r, g, b, 255),
            checkerboard=True,
        )

    def _update_bright_gradient(self, c: RGBA) -> None:
        """Brightness slider: black → current hue/sat at full value."""
        r, g, b, _ = c
        h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        rr, gg, bb = colorsys.hsv_to_rgb(h, max(s, 0.1), 1.0)
        self.bright_slider.set_two_color(
            QColor(0, 0, 0),
            QColor(int(rr * 255), int(gg * 255), int(bb * 255)),
        )

    def _update_harmony(self, c: RGBA) -> None:
        pairs = _harmony_colors(c)
        for (label, sw), (_lbl, hc) in zip(self._harmony_swatches, pairs):
            sw.set_color(hc)