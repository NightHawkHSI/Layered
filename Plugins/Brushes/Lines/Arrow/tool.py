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

class ArrowTool(Tool):
    """Straight line with a filled arrowhead at the tip.
    Press to set the tail, drag/release to set the tip."""
    name = "Arrow"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.head_size  = 20  # arrowhead length in pixels
        self.head_spread = 4  # arrowhead spread (tenths: 4 = 0.4)

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField
        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)
        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px;"); return l
        row.addWidget(lbl('Line Width'))
        _s = SliderField(1, 50, max(1, int(ctx.brush_size)), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Head Size'))
        _s = SliderField(5, 80, int(self.head_size), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'head_size', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Head Spread'))
        _s = SliderField(1, 10, int(self.head_spread), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'head_spread', int(v)))
        row.addWidget(_s)
        row.addStretch()
        return host

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snap = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snap.copy()
        self._render(layer, self._origin, (x, y))
        _clip(layer, self.ctx, self._snap)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snap.copy()
        self._render(layer, self._origin, (x, y))
        _clip(layer, self.ctx, self._snap)
        self._origin = None
        super().release(layer, x, y)

    def _render(self, layer: Layer, p0, p1) -> None:
        x0, y0 = p0
        x1, y1 = p1
        w = max(1, self.ctx.brush_size)
        d = ImageDraw.Draw(layer.image)
        d.line([(x0, y0), (x1, y1)], fill=self.ctx.primary_color, width=w)
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln < 4:
            return
        ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
        h  = max(10, self.head_size)
        sp = max(0.1, self.head_spread / 10.0)
        lx = x1 - h * (ux - sp * uy)
        ly = y1 - h * (uy + sp * ux)
        rx = x1 - h * (ux + sp * uy)
        ry = y1 - h * (uy - sp * ux)
        d.polygon([(x1, y1), (int(lx), int(ly)), (int(rx), int(ry))],
                  fill=self.ctx.primary_color)

TOOL_CLASS = ArrowTool
