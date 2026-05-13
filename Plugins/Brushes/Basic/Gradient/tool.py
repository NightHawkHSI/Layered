"""Gradient tool.

Click-drag to define start/end of a gradient. Live preview during drag,
commits on release. Shift snaps to 45°.

Supported modes
---------------
  Linear    – classic directional fade
  Radial    – circular fade from centre outward
  Reflected – mirror of Linear (primary→secondary→primary)
  Conical   – angular sweep around the start point (like a colour wheel)
  Diamond   – Chebyshev-distance (rotated-square) fade
  Spiral    – conical + radial combined; drag length controls tightness

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
# Colour helpers
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
    """Precompute *steps* RGBA stops between c0 and c1."""
    if reverse:
        c0, c1 = c1, c0
    return [_lerp_color(c0, c1, i / (steps - 1)) for i in range(steps)]


def _build_reflected_lut(c0, c1, reverse: bool, steps: int = 256):
    """LUT that goes c0→c1→c0 (mirrored), for Reflected mode."""
    if reverse:
        c0, c1 = c1, c0
    half = steps // 2
    lut = [_lerp_color(c0, c1, i / (half - 1)) for i in range(half)]
    lut += lut[::-1]
    if len(lut) < steps:
        lut.append(lut[-1])
    return lut[:steps]


def _lut_to_numpy(lut):
    """Convert a Python list-of-tuples LUT to a uint8 numpy array."""
    import numpy as np
    return np.asarray(lut, dtype=np.uint8)


# -------------------------------------------------------------------------
# Geometry helpers
# -------------------------------------------------------------------------

def _snap_45(x0: float, y0: float, x1: float, y1: float):
    dx, dy = x1 - x0, y1 - y0
    angle = math.degrees(math.atan2(dy, dx))
    snap  = round(angle / 45.0) * 45.0
    rad   = math.radians(snap)
    length = math.hypot(dx, dy)
    return x0 + math.cos(rad) * length, y0 + math.sin(rad) * length


# -------------------------------------------------------------------------
# Per-mode builders (numpy fast path + PIL fallback)
# -------------------------------------------------------------------------

class _Builders:
    """Static factory methods – one per gradient mode."""

    # ── Linear ──────────────────────────────────────────────────────────

    @staticmethod
    def linear(w, h, x0, y0, x1, y1, lut):
        try:
            import numpy as np
        except ImportError:
            return _Builders._linear_pil(w, h, x0, y0, x1, y1, lut)

        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        ys, xs = np.mgrid[0:h, 0:w]
        t = ((xs - x0) * dx + (ys - y0) * dy) / length_sq
        np.clip(t, 0.0, 1.0, out=t)
        idx = (t * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _linear_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        dx, dy = x1 - x0, y1 - y0
        lsq = dx * dx + dy * dy or 1.0
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / lsq))
                px[x, y] = lut[int(t * last)]
        return img

    # ── Reflected (mirror linear) ────────────────────────────────────────

    @staticmethod
    def reflected(w, h, x0, y0, x1, y1, lut):
        """Like linear but t is folded: 0→1 maps to 0→1→0 (c0→c1→c0)."""
        try:
            import numpy as np
        except ImportError:
            return _Builders._reflected_pil(w, h, x0, y0, x1, y1, lut)

        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[0]))

        ys, xs = np.mgrid[0:h, 0:w]
        # raw signed projection [-∞, ∞]
        raw = ((xs - x0) * dx + (ys - y0) * dy) / length_sq
        # fold: 1→0.5→1 becomes 0→1→0
        t = 1.0 - np.abs(np.clip(raw, -1.0, 1.0))
        # t is now 1 at origin, 0 at ±end. Remap so origin=0:
        t = 1.0 - t                  # 0 at origin, 1 at both ends
        # Reflect: squash |raw| into [0,1]
        t2 = np.abs(np.clip(raw, 0.0, 1.0))
        # Proper fold: 0→0.5→0 mirrored
        t_fold = 1.0 - np.abs(2.0 * np.clip(raw, -1.0, 1.0) - 1.0) / 1.0
        # Simple & correct fold:
        r = np.abs(raw)
        t_final = np.where(r >= 1.0, 1.0, r)   # clamp at 1 outside range
        # Fold back inward on the negative side
        t_fold2 = np.minimum(np.abs(raw), 1.0)
        np.clip(t_fold2, 0.0, 1.0, out=t_fold2)
        idx = (t_fold2 * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _reflected_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        dx, dy = x1 - x0, y1 - y0
        lsq = dx * dx + dy * dy or 1.0
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                raw = ((x - x0) * dx + (y - y0) * dy) / lsq
                t = min(abs(raw), 1.0)
                px[x, y] = lut[int(t * last)]
        return img

    # ── Radial ───────────────────────────────────────────────────────────

    @staticmethod
    def radial(w, h, x0, y0, x1, y1, lut):
        try:
            import numpy as np
        except ImportError:
            return _Builders._radial_pil(w, h, x0, y0, x1, y1, lut)

        radius = math.hypot(x1 - x0, y1 - y0)
        if radius < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        ys, xs = np.mgrid[0:h, 0:w]
        d = np.sqrt((xs - x0) ** 2 + (ys - y0) ** 2) / radius
        np.clip(d, 0.0, 1.0, out=d)
        idx = (d * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _radial_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        radius = math.hypot(x1 - x0, y1 - y0) or 1.0
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                d = min(math.hypot(x - x0, y - y0) / radius, 1.0)
                px[x, y] = lut[int(d * last)]
        return img

    # ── Diamond (Chebyshev / rotated square) ─────────────────────────────

    @staticmethod
    def diamond(w, h, x0, y0, x1, y1, lut):
        """t = max(|dx_norm|, |dy_norm|) – gives a rotated-square falloff."""
        try:
            import numpy as np
        except ImportError:
            return _Builders._diamond_pil(w, h, x0, y0, x1, y1, lut)

        # Rotate coordinate system so the drag direction is the "x-axis".
        radius = math.hypot(x1 - x0, y1 - y0)
        if radius < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        angle = math.atan2(y1 - y0, x1 - x0)
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)

        ys, xs = np.mgrid[0:h, 0:w]
        rx = (xs - x0) * cos_a - (ys - y0) * sin_a
        ry = (xs - x0) * sin_a + (ys - y0) * cos_a

        d = np.maximum(np.abs(rx), np.abs(ry)) / radius
        np.clip(d, 0.0, 1.0, out=d)
        idx = (d * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _diamond_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        radius = math.hypot(x1 - x0, y1 - y0) or 1.0
        angle = math.atan2(y1 - y0, x1 - x0)
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                rx = (x - x0) * cos_a - (y - y0) * sin_a
                ry = (x - x0) * sin_a + (y - y0) * cos_a
                d = min(max(abs(rx), abs(ry)) / radius, 1.0)
                px[x, y] = lut[int(d * last)]
        return img

    # ── Conical (angle sweep) ─────────────────────────────────────────────

    @staticmethod
    def conical(w, h, x0, y0, x1, y1, lut):
        """Angular sweep centred on (x0,y0); drag sets the 0° reference."""
        try:
            import numpy as np
        except ImportError:
            return _Builders._conical_pil(w, h, x0, y0, x1, y1, lut)

        ref_angle = math.atan2(y1 - y0, x1 - x0)

        ys, xs = np.mgrid[0:h, 0:w]
        angles = np.arctan2(ys - y0, xs - x0) - ref_angle
        # Wrap into [0, 2π]
        angles = angles % (2 * math.pi)
        t = angles / (2 * math.pi)
        idx = (t * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _conical_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        ref = math.atan2(y1 - y0, x1 - x0)
        tau = 2 * math.pi
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                a = (math.atan2(y - y0, x - x0) - ref) % tau
                px[x, y] = lut[int((a / tau) * last)]
        return img

    # ── Spiral ────────────────────────────────────────────────────────────

    @staticmethod
    def spiral(w, h, x0, y0, x1, y1, lut):
        """t = (angle / 2π + radial_distance) mixed; drag length = 1 turn."""
        try:
            import numpy as np
        except ImportError:
            return _Builders._spiral_pil(w, h, x0, y0, x1, y1, lut)

        radius = math.hypot(x1 - x0, y1 - y0)
        if radius < 1e-6:
            return Image.new("RGBA", (w, h), tuple(lut[-1]))

        ref_angle = math.atan2(y1 - y0, x1 - x0)

        ys, xs = np.mgrid[0:h, 0:w]
        angles = (np.arctan2(ys - y0, xs - x0) - ref_angle) % (2 * math.pi)
        dist   = np.sqrt((xs - x0) ** 2 + (ys - y0) ** 2) / radius

        # Combine: one full revolution = one full radius step
        t = (angles / (2 * math.pi) + dist) % 1.0
        idx = (t * (len(lut) - 1)).astype(np.uint16)
        return Image.fromarray(_lut_to_numpy(lut)[idx], "RGBA")

    @staticmethod
    def _spiral_pil(w, h, x0, y0, x1, y1, lut):
        img = Image.new("RGBA", (w, h), tuple(lut[0]))
        radius = math.hypot(x1 - x0, y1 - y0) or 1.0
        ref = math.atan2(y1 - y0, x1 - x0)
        tau = 2 * math.pi
        px, last = img.load(), len(lut) - 1
        for y in range(h):
            for x in range(w):
                a = (math.atan2(y - y0, x - x0) - ref) % tau
                d = math.hypot(x - x0, y - y0) / radius
                t = (a / tau + d) % 1.0
                px[x, y] = lut[int(t * last)]
        return img


# -------------------------------------------------------------------------
# Mode registry  {display_name: (builder_fn, uses_reflected_lut)}
# -------------------------------------------------------------------------

MODES = {
    "Linear":    (_Builders.linear,    False),
    "Reflected": (_Builders.reflected, True),
    "Radial":    (_Builders.radial,    False),
    "Diamond":   (_Builders.diamond,   False),
    "Conical":   (_Builders.conical,   False),
    "Spiral":    (_Builders.spiral,    False),
}

MODE_NAMES = list(MODES.keys())


# -------------------------------------------------------------------------
# Handle hit-testing
# -------------------------------------------------------------------------

_HIT_RADIUS_CANVAS = 12   # canvas-space pixels; generous enough at any zoom


def _hit_handle(px, py, handles):
    """Return the key of the nearest handle within _HIT_RADIUS_CANVAS, or None."""
    best_key, best_d = None, _HIT_RADIUS_CANVAS
    for key, (hx, hy) in handles.items():
        d = math.hypot(px - hx, py - hy)
        if d < best_d:
            best_d, best_key = d, key
    return best_key


# -------------------------------------------------------------------------
# Gradient Tool
# -------------------------------------------------------------------------

class GradientTool(Tool):
    """Gradient tool with persistent, draggable start/end handles.

    After drawing a gradient, both endpoints stay visible as draggable
    handles.  Click-drag either one to adjust the gradient non-destructively.
    Click-drag on empty canvas space to start a fresh gradient (the previous
    one is composited into the layer's base state first).

    Drag states
    -----------
      None  – idle; handles visible but no pointer interaction
      "p0"  – dragging the start handle
      "p1"  – dragging the end handle
      "new" – drawing a brand-new gradient stroke
    """

    name      = "Gradient"
    tool_id   = "gradient"
    icon      = "🌈"
    shortcut  = "G"
    group     = "Basic"
    commit_on = "release"

    # Colours used in the overlay
    _COL_IDLE    = QColor(0,   200, 255)        # cyan  – resting handle
    _COL_ACTIVE  = QColor(255, 180,   0)        # amber – handle being dragged
    _COL_MIRROR  = QColor(180, 100, 255)        # violet – Reflected mirror point
    _COL_GUIDE   = QColor(255, 255, 255, 180)   # white dashed guide line

    def __init__(self, ctx=None):
        super().__init__(ctx)

        self.opacity = 1.0
        self.mode    = "Linear"
        self.reverse = False

        # Persistent across mouse events:
        self._snapshot    = None    # Image.Image – layer state before this gradient
        self._p0          = None    # (canvas_x, canvas_y) – start / centre handle
        self._p1          = None    # (canvas_x, canvas_y) – end / radius handle

        # Per-drag:
        self._drag_target = None    # "p0" | "p1" | "new" | None
        self._layer_ref   = None    # Layer being edited (kept for re-render on UI change)

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
        mode_cb = QComboBox()
        mode_cb.addItems(MODE_NAMES)
        mode_cb.setCurrentText(self.mode)
        mode_cb.setMinimumWidth(90)
        mode_cb.currentTextChanged.connect(self._on_mode_changed)
        row.addWidget(mode_cb)

        row.addWidget(QLabel("Opacity"))
        op = SliderField(1, 100, int(self.opacity * 100), suffix="%")
        op.setMinimumWidth(120)
        op.valueChanged.connect(self._on_opacity_changed)
        row.addWidget(op, 1)

        rev = QCheckBox("Reverse")
        rev.setChecked(self.reverse)
        rev.toggled.connect(self._on_reverse_changed)
        row.addWidget(rev)

        row.addStretch(1)
        return w

    def _on_mode_changed(self, text: str) -> None:
        self.mode = text
        self._re_render()

    def _on_opacity_changed(self, v: int) -> None:
        self.opacity = v / 100.0
        self._re_render()

    def _on_reverse_changed(self, v: bool) -> None:
        self.reverse = bool(v)
        self._re_render()

    def _re_render(self) -> None:
        """Re-render when a UI control changes while handles are live."""
        if self._layer_ref is not None and self._snapshot is not None:
            self._render(self._layer_ref)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def _effective_points(self):
        """Return (x0, y0, x1, y1) in canvas space, with snap applied."""
        x0, y0 = self._p0
        x1, y1 = self._p1
        if self.ctx.shift_held:
            if self._drag_target in ("p1", "new"):
                x1, y1 = _snap_45(x0, y0, x1, y1)
            elif self._drag_target == "p0":
                x0, y0 = _snap_45(x1, y1, x0, y0)
        return x0, y0, x1, y1

    def _render(self, layer: Layer) -> None:
        if self._snapshot is None or self._p0 is None or self._p1 is None:
            return

        base = self._snapshot.copy()
        w, h = base.size

        ox, oy = layer.offset
        cx0, cy0, cx1, cy1 = self._effective_points()
        x0, y0 = cx0 - ox, cy0 - oy
        x1, y1 = cx1 - ox, cy1 - oy

        c0 = self.ctx.primary_color
        c1 = self.ctx.secondary_color

        builder_fn, uses_reflected_lut = MODES[self.mode]
        lut = (_build_reflected_lut if uses_reflected_lut else _build_lut)(
            c0, c1, self.reverse
        )

        grad = builder_fn(w, h, x0, y0, x1, y1, lut)

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

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._layer_ref = layer

        # If handles exist, check whether the click is on one.
        if self._snapshot is not None and self._p0 is not None:
            hit = _hit_handle(x, y, {"p0": self._p0, "p1": self._p1})
            if hit is not None:
                self._drag_target = hit
                return   # Start dragging existing handle – no new snapshot needed

        # ── New gradient ─────────────────────────────────────────────────
        # layer.image currently has the previous gradient baked in (if any),
        # so snapshot it as the new base.
        self._snapshot    = layer.image.copy()
        self._p0          = (x, y)
        self._p1          = (x, y)
        self._drag_target = "new"
        self._render(layer)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._drag_target is None or self._p0 is None:
            return
        if self._drag_target == "p0":
            self._p0 = (x, y)
        else:                       # "p1" or "new"
            self._p1 = (x, y)
        self._render(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._drag_target is None or self._p0 is None:
            return
        if self._drag_target == "p0":
            self._p0 = (x, y)
        else:
            self._p1 = (x, y)
        self._render(layer)
        self._drag_target = None
        # ── Keep _snapshot / _p0 / _p1 alive so handles remain draggable. ──

    def cancel(self) -> None:
        """Discard the in-progress gradient and clear all state."""
        self._snapshot    = None
        self._p0          = None
        self._p1          = None
        self._drag_target = None
        self._layer_ref   = None

    # ------------------------------------------------------------------
    # Overlay  –  mode-aware guide + styled handles
    # ------------------------------------------------------------------

    def _draw_handle(self, painter, pt: QPointF, role: str) -> None:
        """Draw a single handle circle.

        role – "active" | "idle"
        """
        if role == "active":
            col   = self._COL_ACTIVE
            outer = 8.0
            inner = 4.0
            pen_w = 2.5
        else:
            col   = self._COL_IDLE
            outer = 6.0
            inner = 2.5
            pen_w = 2.0

        # White shadow ring for contrast on any background
        painter.setPen(QPen(QColor(0, 0, 0, 120), pen_w + 2))
        painter.drawEllipse(pt, outer, outer)
        # Coloured ring
        painter.setPen(QPen(col, pen_w))
        painter.drawEllipse(pt, outer, outer)
        # Filled centre dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(col)
        painter.drawEllipse(pt, inner, inner)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def paint_overlay(self, painter, canvas) -> None:
        if self._p0 is None or self._p1 is None:
            return

        cx0, cy0, cx1, cy1 = self._effective_points()

        x0s, y0s = canvas.canvas_to_screen(cx0, cy0)
        x1s, y1s = canvas.canvas_to_screen(cx1, cy1)
        p0 = QPointF(x0s, y0s)
        p1 = QPointF(x1s, y1s)

        role_p0 = "active" if self._drag_target == "p0" else "idle"
        role_p1 = "active" if self._drag_target in ("p1", "new") else "idle"

        # ── Mode-specific guide geometry ─────────────────────────────────

        if self.mode == "Radial":
            radius_px = math.hypot(x1s - x0s, y1s - y0s)
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(QColor(0, 200, 255, 100), 1.2, Qt.PenStyle.DashLine))
            painter.drawEllipse(p0, radius_px, radius_px)

        elif self.mode == "Diamond":
            radius_px = math.hypot(x1s - x0s, y1s - y0s)
            angle = math.atan2(y1s - y0s, x1s - x0s)
            corners = [
                QPointF(x0s + math.cos(angle + i * math.pi / 2) * radius_px,
                        y0s + math.sin(angle + i * math.pi / 2) * radius_px)
                for i in range(4)
            ]
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(QColor(0, 200, 255, 100), 1.2, Qt.PenStyle.DashLine))
            for i in range(4):
                painter.drawLine(corners[i], corners[(i + 1) % 4])

        elif self.mode == "Conical":
            from PyQt6.QtCore import QRectF
            r_px = max(24.0, math.hypot(x1s - x0s, y1s - y0s) * 0.35)
            ref_deg = math.degrees(math.atan2(y1s - y0s, x1s - x0s))
            rect = QRectF(x0s - r_px, y0s - r_px, r_px * 2, r_px * 2)
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(QColor(0, 200, 255, 130), 1.5, Qt.PenStyle.DashLine))
            painter.drawArc(rect, int(-ref_deg * 16), int(300 * 16))

        elif self.mode == "Spiral":
            steps = 56
            radius_px = math.hypot(x1s - x0s, y1s - y0s)
            ref_angle  = math.atan2(y1s - y0s, x1s - x0s)
            pts = [
                QPointF(x0s + math.cos(ref_angle + (i / steps) * 2 * math.pi)
                             * (i / steps) * radius_px * 0.65,
                        y0s + math.sin(ref_angle + (i / steps) * 2 * math.pi)
                             * (i / steps) * radius_px * 0.65)
                for i in range(steps + 1)
            ]
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p0, p1)
            painter.setPen(QPen(QColor(0, 200, 255, 150), 1.3, Qt.PenStyle.DashLine))
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])

        elif self.mode == "Reflected":
            # Mirror line extends symmetrically through p0
            mx, my = 2 * x0s - x1s, 2 * y0s - y1s
            pm = QPointF(mx, my)
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(pm, p1)
            # Mirror handle (violet) – not draggable, purely informational
            painter.setPen(QPen(self._COL_MIRROR, 2))
            painter.drawEllipse(pm, 5, 5)

        else:   # Linear (and any future modes)
            painter.setPen(QPen(self._COL_GUIDE, 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p0, p1)

        # ── Handles (drawn last so they sit on top) ──────────────────────
        self._draw_handle(painter, p0, role_p0)
        self._draw_handle(painter, p1, role_p1)


# -------------------------------------------------------------------------
# Required export
# -------------------------------------------------------------------------

TOOL_CLASS = GradientTool