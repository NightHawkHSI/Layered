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

class SprayBrushTool(Tool):
    """Airbrush / spray-paint: scatters random pixels inside the brush radius.
    Density scales with opacity; radius scales with brush size."""
    name = "Spray"
    icon = "💨"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.density    = 5    # dots per stamp
        self.spread_pct = 100  # scatter radius as % of brush radius

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField
        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)
        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px;"); return l
        row.addWidget(lbl('Size'))
        _s = SliderField(1, 500, max(1, int(ctx.brush_size)), slider_width=100)
        _s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Opacity'))
        _s = SliderField(1, 100, max(1, int(ctx.brush_opacity)), slider_width=100)
        _s.valueChanged.connect(lambda v: setattr(ctx, 'brush_opacity', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Density'))
        _s = SliderField(1, 20, int(self.density), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'density', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Spread %'))
        _s = SliderField(10, 300, int(self.spread_pct), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'spread_pct', int(v)))
        row.addWidget(_s)
        row.addStretch()
        return host

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._spray(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        spacing = max(1.0, self.ctx.brush_size * 0.25)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._spray(layer, px, py)
        self._last_pt = (x, y)

    def _spray(self, layer: Layer, x: int, y: int) -> None:
        r       = max(1, int(self.ctx.brush_size * self.spread_pct / 100) // 2)
        density = max(1, self.density)
        ox, oy  = layer.offset
        d       = ImageDraw.Draw(layer.image)
        for _ in range(density):
            angle = random.uniform(0.0, 2.0 * math.pi)
            dist  = random.uniform(0.0, r)
            px = int(x - ox + dist * math.cos(angle))
            py = int(y - oy + dist * math.sin(angle))
            if 0 <= px < layer.image.width and 0 <= py < layer.image.height:
                d.point((px, py), fill=self.ctx.primary_color)

TOOL_CLASS = SprayBrushTool
