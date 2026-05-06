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

class CurveTool(Tool):
    """Quadratic Bezier curve.
    Press = anchor start. Drag = pull the control point (live preview).
    Release = anchor end and commit."""
    name = "Curve"
    commit_on = "release"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._start = (x, y)
        self._ctrl  = (x, y)
        self._snap  = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_start", None):
            return
        self._ctrl = (x, y)
        layer.image = self._snap.copy()
        self._render(layer, self._start, self._ctrl, self._ctrl)
        _clip(layer, self.ctx, self._snap)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_start", None):
            return
        layer.image = self._snap.copy()
        self._render(layer, self._start, self._ctrl, (x, y))
        _clip(layer, self.ctx, self._snap)
        self._start = None
        super().release(layer, x, y)

    def _render(self, layer: Layer, s, ctrl, e) -> None:
        sx, sy = s
        cx, cy = ctrl
        ex, ey = e
        steps = max(32, int(math.hypot(ex - sx, ey - sy)
                            + math.hypot(cx - sx, cy - sy)))
        pts = []
        for i in range(steps + 1):
            t = i / max(1, steps)
            mt = 1.0 - t
            pts.append((
                int(mt * mt * sx + 2 * mt * t * cx + t * t * ex),
                int(mt * mt * sy + 2 * mt * t * cy + t * t * ey),
            ))
        if len(pts) >= 2:
            ImageDraw.Draw(layer.image).line(
                pts, fill=self.ctx.primary_color,
                width=max(1, self.ctx.brush_size))

TOOL_CLASS = CurveTool
