import importlib.util, math, sys
from pathlib import Path
from PIL import Image, ImageDraw
from app.layer import Layer
from app.tools import Tool

_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_walk = sys.modules[_K]._walk


def _rot(px, py, cx, cy, cos_a, sin_a):
    dx, dy = px - cx, py - cy
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


def _refl(px, py, cx, cy, cos_a, sin_a):
    """Reflect a point across an axis through (cx,cy) with direction (cos_a,sin_a)."""
    dx, dy = px - cx, py - cy
    dot = dx * cos_a + dy * sin_a
    return cx + 2 * dot * cos_a - dx, cy + 2 * dot * sin_a - dy


class KaleidoscopeBrushTool(Tool):
    """Kaleidoscope / mandala brush.

    Every stroke segment is replicated N times, rotated evenly around the
    point where you first pressed.  Enabling Mirror also reflects each copy
    across its own axis, doubling the symmetry and producing true mandala
    patterns.  Use any other brush shape underneath — this tool replicates
    whatever the base tool draws.

    Settings
    --------
    Axes    – number of symmetry copies (2–24)
    Mirror  – also reflect each copy (0=off, 1=on)
    Size    – brush tip radius in px (1–40)
    Opacity – per-segment opacity (driven by brush_opacity too)
    """

    name = "Kaleidoscope"
    icon = "❋"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.axes    = 8
        self.mirror  = 1
        self.tip_size = 6

        self._center: tuple[float, float] = (0.0, 0.0)
        self._last_pt: tuple[float, float] | None = None

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField

        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px;")
            return l

        for attr, label, lo, hi, w in [
            ("axes",     "Axes",    2, 24, 75),
            ("mirror",   "Mirror",  0,  1, 55),
            ("tip_size", "Size",    1, 40, 75),
        ]:
            row.addWidget(lbl(label))
            s = SliderField(lo, hi, getattr(self, attr), slider_width=w)
            s.valueChanged.connect(lambda v, a=attr: setattr(self, a, int(v)))
            row.addWidget(s)

        row.addStretch()
        return host

    def _spacing(self):
        return max(1.0, self.tip_size * 0.4)

    def press(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        self._center  = (x - ox, y - oy)   # fixed symmetry hub in layer coords
        self._last_pt = (x - ox, y - oy)
        self._dot(layer, x - ox, y - oy)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            return
        ox, oy = layer.offset
        cur = (x - ox, y - oy)
        spacing = self._spacing()
        # walk in canvas coords then convert
        for px, py in _walk(
            (self._last_pt[0] + ox, self._last_pt[1] + oy),
            (cur[0] + ox, cur[1] + oy),
            spacing,
        ):
            self._segment(layer, self._last_pt, (px - ox, py - oy))
            self._last_pt = (px - ox, py - oy)
        self._last_pt = cur

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    # ── drawing ───────────────────────────────────────────────────────────────
    def _draw_line_all(self, draw, x0, y0, x1, y1, color, width):
        """Draw a segment and all its symmetry copies."""
        cx, cy = self._center
        for i in range(self.axes):
            angle   = 2 * math.pi * i / self.axes
            cos_a   = math.cos(angle)
            sin_a   = math.sin(angle)
            rx0, ry0 = _rot(x0, y0, cx, cy, cos_a, sin_a)
            rx1, ry1 = _rot(x1, y1, cx, cy, cos_a, sin_a)
            draw.line([(round(rx0), round(ry0)), (round(rx1), round(ry1))],
                      fill=color, width=width)
            if self.mirror:
                # axis direction for this slice
                mid_angle = angle + math.pi / self.axes
                ac, as_   = math.cos(mid_angle), math.sin(mid_angle)
                mx0, my0  = _refl(rx0, ry0, cx, cy, ac, as_)
                mx1, my1  = _refl(rx1, ry1, cx, cy, ac, as_)
                draw.line([(round(mx0), round(my0)), (round(mx1), round(my1))],
                          fill=color, width=width)

    def _segment(self, layer: Layer, p0, p1) -> None:
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        draw    = ImageDraw.Draw(layer.image)
        width   = max(1, self.tip_size)
        self._draw_line_all(draw, p0[0], p0[1], p1[0], p1[1],
                            (r, g, b, alpha), width)

    def _dot(self, layer: Layer, lx: float, ly: float) -> None:
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        draw    = ImageDraw.Draw(layer.image)
        tr      = max(1, self.tip_size // 2)
        cx, cy  = self._center
        for i in range(self.axes):
            angle  = 2 * math.pi * i / self.axes
            cos_a  = math.cos(angle)
            sin_a  = math.sin(angle)
            rx, ry = _rot(lx, ly, cx, cy, cos_a, sin_a)
            draw.ellipse([round(rx - tr), round(ry - tr),
                          round(rx + tr), round(ry + tr)],
                         fill=(r, g, b, alpha))
            if self.mirror:
                mid_angle = angle + math.pi / self.axes
                ac, as_   = math.cos(mid_angle), math.sin(mid_angle)
                mx, my    = _refl(rx, ry, cx, cy, ac, as_)
                draw.ellipse([round(mx - tr), round(my - tr),
                              round(mx + tr), round(my + tr)],
                             fill=(r, g, b, alpha))


TOOL_CLASS = KaleidoscopeBrushTool