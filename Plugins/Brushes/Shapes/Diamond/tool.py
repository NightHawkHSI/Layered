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

class DiamondTool(_ST):
    """Diamond / rhombus inscribed in the drag bbox."""
    name = "Diamond"

    def _draw(self, layer: Layer, bbox):
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        pts = [(cx, y0), (x1, cy), (cx, y1), (x0, cy)]
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.polygon(pts, fill=self.ctx.primary_color,
                      outline=self.ctx.primary_color)
        else:
            d.polygon(pts, outline=self.ctx.primary_color,
                      width=max(1, self.ctx.brush_size))

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
        row.addWidget(lbl('Size'))
        s = SliderField(1, 200, max(1, int(ctx.brush_size)), slider_width=120)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = DiamondTool
