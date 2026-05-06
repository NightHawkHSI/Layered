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

class HexagonTool(_ST):
    """Regular hexagon inscribed in the drag bbox."""
    name = "Hexagon"

    def _draw(self, layer: Layer, bbox):
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        pts = [
            (int(cx + rx * math.cos(math.pi * 2 * i / 6 - math.pi / 2)),
             int(cy + ry * math.sin(math.pi * 2 * i / 6 - math.pi / 2)))
            for i in range(6)
        ]
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.polygon(pts, fill=self.ctx.primary_color,
                      outline=self.ctx.primary_color)
        else:
            d.polygon(pts, outline=self.ctx.primary_color,
                      width=max(1, self.ctx.brush_size))

TOOL_CLASS = HexagonTool
