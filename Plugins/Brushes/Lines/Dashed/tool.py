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

class DashedLineTool(Tool):
    """Dashed straight line from press to release."""
    name = "Dashed Line"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.dash_mult = 4  # dash = line_width * dash_mult
        self.gap_mult  = 2  # gap  = line_width * gap_mult

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
        row.addWidget(lbl('Dash'))
        _s = SliderField(1, 20, int(self.dash_mult), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'dash_mult', int(v)))
        row.addWidget(_s)
        row.addWidget(lbl('Gap'))
        _s = SliderField(1, 20, int(self.gap_mult), slider_width=90)
        _s.valueChanged.connect(lambda v: setattr(self, 'gap_mult', int(v)))
        row.addWidget(_s)
        row.addStretch()
        return host

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snap   = layer.image.copy()

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
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1:
            return
        w      = max(1, self.ctx.brush_size)
        dash   = max(2, w * self.dash_mult)
        gap    = max(1, w * self.gap_mult)
        period = dash + gap
        d = ImageDraw.Draw(layer.image)
        t = 0.0
        while t < ln:
            t0 = t / ln
            t1 = min((t + dash) / ln, 1.0)
            d.line(
                [(int(x0 + dx * t0), int(y0 + dy * t0)),
                 (int(x0 + dx * t1), int(y0 + dy * t1))],
                fill=self.ctx.primary_color, width=w,
            )
            t += period

TOOL_CLASS = DashedLineTool
