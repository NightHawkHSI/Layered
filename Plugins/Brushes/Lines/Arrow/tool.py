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
        h = max(10, w * 5)
        sp = 0.4
        lx = x1 - h * (ux - sp * uy)
        ly = y1 - h * (uy + sp * ux)
        rx = x1 - h * (ux + sp * uy)
        ry = y1 - h * (uy - sp * ux)
        d.polygon([(x1, y1), (int(lx), int(ly)), (int(rx), int(ry))],
                  fill=self.ctx.primary_color)

TOOL_CLASS = ArrowTool
