import importlib.util, math, sys, random
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
_bt = sys.modules[_K]
_ST   = _bt._ShapeTool
_walk = _bt._walk
_clip = _bt._clip_layer_to_selection


class ScatterBrushTool(Tool):
    """Scatter brush: random dots along the stroke.
    Settings: Density (dots per stamp), Spread (radius %), Max Dot Size."""
    name = "Scatter"
    icon = "✣"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.density      = 5
        self.spread_pct   = 100
        self.max_dot_size = 4

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

        row.addWidget(lbl("Density"))
        s_den = SliderField(1, 20, self.density, slider_width=90)
        s_den.valueChanged.connect(lambda v: setattr(self, "density", int(v)))
        row.addWidget(s_den)

        row.addWidget(lbl("Spread %"))
        s_spr = SliderField(10, 300, self.spread_pct, slider_width=90)
        s_spr.valueChanged.connect(lambda v: setattr(self, "spread_pct", int(v)))
        row.addWidget(s_spr)

        row.addWidget(lbl("Dot Size"))
        s_dot = SliderField(1, 20, self.max_dot_size, slider_width=90)
        s_dot.valueChanged.connect(lambda v: setattr(self, "max_dot_size", int(v)))
        row.addWidget(s_dot)

        row.addStretch()
        return host

    def _spacing(self):
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing * 0.4)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._scatter(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._scatter(layer, px, py)
        self._last_pt = (x, y)

    def _scatter(self, layer, x, y):
        ox, oy  = layer.offset
        br      = max(1, self.ctx.brush_size // 2)
        r       = max(1, int(br * self.spread_pct / 100))
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        c       = self.ctx.primary_color[:3] + (alpha,)
        for _ in range(max(1, self.density)):
            jx   = int(x - ox + random.uniform(-r, r))
            jy   = int(y - oy + random.uniform(-r, r))
            size = random.randint(1, max(1, self.max_dot_size))
            dot  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ImageDraw.Draw(dot).ellipse([0, 0, size - 1, size - 1], fill=c)
            if 0 <= jx < layer.image.width and 0 <= jy < layer.image.height:
                layer.image.alpha_composite(dot, dest=(jx, jy))


TOOL_CLASS = ScatterBrushTool
