"""Gradient tool.

Click-drag to define start/end of a gradient. Live preview during drag,
commits on release. Supports Linear and Radial; Shift snaps to 45°.
Fills primary → secondary across the stroke (alpha-blended within
selection if one exists).
"""
import importlib.util as _iu, sys as _sys
from pathlib import Path as _P

# -------------------------------------------------------------------------
# Shared imports loader
# -------------------------------------------------------------------------

_SHARED_KEY = "_layered_brushes_shared"

if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)

_sh = _sys.modules[_SHARED_KEY]

Tool                    = _sh.Tool
ToolContext             = _sh.ToolContext
Layer                   = _sh.Layer
Image                   = _sh.Image
ImageChops              = _sh.ImageChops
ImageDraw               = _sh.ImageDraw
SliderField             = _sh.SliderField
QWidget                 = _sh.QWidget
QHBoxLayout             = _sh.QHBoxLayout
QLabel                  = _sh.QLabel
QComboBox               = _sh.QComboBox
QCheckBox               = _sh.QCheckBox
Qt                      = _sh.Qt
QPen                    = _sh.QPen
QColor                  = _sh.QColor
QPointF                 = _sh.QPointF
_selection_at_layer     = _sh._selection_at_layer
math                    = _sh.math


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(c0, c1, t: float):
    return (
        int(round(_lerp(c0[0], c1[0], t))),
        int(round(_lerp(c0[1], c1[1], t))),
        int(round(_lerp(c0[2], c1[2], t))),
        int(round(_lerp(c0[3], c1[3], t))),
    )


def _build_lut(c0, c1, reverse: bool, steps: int = 256):
    """Precompute 256 RGBA stops between c0 and c1."""
    if reverse:
        c0, c1 = c1, c0
    return [_lerp_color(c0, c1, i / (steps - 1)) for i in range(steps)]


def _snap_45(x0: float, y0: float, x1: float, y1: float):
    dx, dy = x1 - x0, y1 - y0
    angle = math.degrees(math.atan2(dy, dx))
    snap = round(angle / 45.0) * 45.0
    rad = math.radians(snap)
    length = math.hypot(dx, dy)
    return x0 + math.cos(rad) * length, y0 + math.sin(rad) * length


# -------------------------------------------------------------------------
# Gradient Tool
# -------------------------------------------------------------------------

class GradientTool(Tool):
    name      = "Gradient"
    tool_id   = "gradient"
    icon      = "🌈"
    shortcut  = "G"
    group     = "Basic"
    commit_on = "release"

    MODE_LINEAR = "Linear"
    MODE_RADIAL = "Radial"

    def __init__(self, ctx=None):
        super().__init__(ctx)

        self.opacity = 1.0
        self.mode    = self.MODE_LINEAR
        self.reverse = False

        self._snapshot = None    # Image.Image
        self._p0       = None    # (x, y)
        self._p1       = None    # (x, y)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self, parent, ctx):
        w = QWidget(parent)
        w.setFixedHeight(28)
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        row.addWidget(QLabel("Mode"))
        mode = QComboBox()
        mode.addItems([self.MODE_LINEAR, self.MODE_RADIAL])
        mode.setCurrentText(self.mode)
        mode.currentTextChanged.connect(self._on_mode)
        row.addWidget(mode)

        row.addWidget(QLabel("Opacity"))
        op = SliderField(1, 100, int(self.opacity * 100), suffix="%")
        op.setMinimumWidth(120)
        op.valueChanged.connect(lambda v: setattr(self, "opacity", v / 100.0))
        row.addWidget(op, 1)

        rev = QCheckBox("Reverse")
        rev.setChecked(self.reverse)
        rev.toggled.connect(lambda v: setattr(self, "reverse", bool(v)))
        row.addWidget(rev)

        row.addStretch(1)
        return w

    def _on_mode(self, text: str) -> None:
        self.mode = text

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _render(self, layer: Layer) -> None:
        """Rebuild layer.image from the snapshot + current gradient."""
        if self._snapshot is None or self._p0 is None or self._p1 is None:
            return

        base = self._snapshot.copy()
        w, h = base.size

        ox, oy = layer.offset
        x0, y0 = self._p0[0] - ox, self._p0[1] - oy
        x1, y1 = self._p1[0] - ox, self._p1[1] - oy

        if self.ctx.shift_held:
            x1, y1 = _snap_45(x0, y0, x1, y1)

        c0 = self.ctx.primary_color
        c1 = self.ctx.secondary_color
        lut = _build_lut(c0, c1, self.reverse)

        if self.mode == self.MODE_RADIAL:
            grad = self._build_radial(w, h, x0, y0, x1, y1, lut)
        else:
            grad = self._build_linear(w, h, x0, y0, x1, y1, lut)

        if self.opacity < 1.0:
            r, g, b, a = grad.split()
            a = a.point(lambda v: int(v * self.opacity))
            grad = Image.merge("RGBA", (r, g, b, a))

        sel = _selection_at_layer(self.ctx, layer)
        if sel is not None:
            r, g, b, a = grad.split()
            a = ImageChops.multiply(a, sel)
            grad = Image.merge("RGBA", (r, g, b, a))

        base.alpha_composite(grad)
        layer.image = base

    @staticmethod
    def _build_linear(w, h, x0, y0, x1, y1, lut):
        try:
            import numpy as np
        except Exception:
            return GradientTool._build_linear_pil(w, h, x0, y0, x1, y1, lut)

        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        ys, xs = np.mgrid[0:h, 0:w]
        t = ((xs - x0) * dx + (ys - y0) * dy) / length_sq
        np.clip(t, 0.0, 1.0, out=t)
        idx = (t * (len(lut) - 1)).astype(np.uint16)

        lut_arr = np.asarray(lut, dtype=np.uint8)  # (256, 4)
        out = lut_arr[idx]                          # (h, w, 4)
        return Image.fromarray(out, mode="RGBA")

    @staticmethod
    def _build_radial(w, h, x0, y0, x1, y1, lut):
        try:
            import numpy as np
        except Exception:
            return GradientTool._build_radial_pil(w, h, x0, y0, x1, y1, lut)

        radius = math.hypot(x1 - x0, y1 - y0)
        if radius < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        ys, xs = np.mgrid[0:h, 0:w]
        d = np.sqrt((xs - x0) ** 2 + (ys - y0) ** 2) / radius
        np.clip(d, 0.0, 1.0, out=d)
        idx = (d * (len(lut) - 1)).astype(np.uint16)

        lut_arr = np.asarray(lut, dtype=np.uint8)
        out = lut_arr[idx]
        return Image.fromarray(out, mode="RGBA")

    @staticmethod
    def _build_linear_pil(w, h, x0, y0, x1, y1, lut):
        # Slow fallback if numpy missing.
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy or 1.0
        px = img.load()
        last = len(lut) - 1
        for y in range(h):
            for x in range(w):
                t = ((x - x0) * dx + (y - y0) * dy) / length_sq
                if t < 0.0: t = 0.0
                elif t > 1.0: t = 1.0
                px[x, y] = lut[int(t * last)]
        return img

    @staticmethod
    def _build_radial_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        radius = math.hypot(x1 - x0, y1 - y0) or 1.0
        px = img.load()
        last = len(lut) - 1
        for y in range(h):
            for x in range(w):
                d = math.hypot(x - x0, y - y0) / radius
                if d > 1.0: d = 1.0
                px[x, y] = lut[int(d * last)]
        return img

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._snapshot = layer.image.copy()
        self._p0 = (x, y)
        self._p1 = (x, y)
        self._render(layer)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._p0 is None:
            return
        self._p1 = (x, y)
        self._render(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._p0 is None:
            return
        self._p1 = (x, y)
        self._render(layer)
        self._snapshot = None
        self._p0 = None
        self._p1 = None

    def cancel(self) -> None:
        self._snapshot = None
        self._p0 = None
        self._p1 = None

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------

    def paint_overlay(self, painter, canvas) -> None:
        if self._p0 is None or self._p1 is None:
            return
        x0, y0 = canvas.canvas_to_screen(self._p0[0], self._p0[1])
        x1, y1 = canvas.canvas_to_screen(self._p1[0], self._p1[1])
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        painter.setPen(QPen(QColor(0, 200, 255), 2))
        painter.drawEllipse(QPointF(x0, y0), 4, 4)
        painter.drawEllipse(QPointF(x1, y1), 4, 4)


# -------------------------------------------------------------------------
# Required export
# -------------------------------------------------------------------------

TOOL_CLASS = GradientTool
