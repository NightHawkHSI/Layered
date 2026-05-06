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
        r       = max(1, self.ctx.brush_size // 2)
        density = max(1, int(r * self.ctx.brush_opacity * 8))
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
