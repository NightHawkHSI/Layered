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

class SquareBrushTool(Tool):
    """Hard-edged square stamp brush - like the round brush but square."""
    name = "Square Brush"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def _stamp(self, layer: Layer, x: int, y: int) -> None:
        s       = max(1, self.ctx.brush_size)
        r       = s // 2
        ox, oy  = layer.offset
        lx, ly  = x - ox, y - oy
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        c       = self.ctx.primary_color[:3] + (alpha,)
        sq      = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(sq).rectangle([0, 0, s - 1, s - 1], fill=c)
        layer.image.alpha_composite(sq, dest=(lx - r, ly - r))

TOOL_CLASS = SquareBrushTool
