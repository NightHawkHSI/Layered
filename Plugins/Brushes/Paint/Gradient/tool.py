import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
import numpy as np
_SHARED_KEY = "_layered_brushes_shared"
if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)
_sh = _sys.modules[_SHARED_KEY]

Tool = _sh.Tool
Layer = _sh.Layer
Image = _sh.Image
ImageChops = _sh.ImageChops
_selection_at_layer = _sh._selection_at_layer


class GradientTool(Tool):
    """Drag to draw a linear gradient from primary -> secondary color."""
    name = "Gradient"
    commit_on = "release"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()
        self._cur = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if getattr(self, "_origin", None) is None:
            return
        self._cur = (x, y)
        self._render(layer, x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if getattr(self, "_origin", None) is None:
            return
        self._render(layer, x, y)
        self._origin = None
        super().release(layer, x, y)

    def _render(self, layer: Layer, x: int, y: int) -> None:
        layer.image = self._snapshot.copy()
        ox, oy = self._origin
        dx, dy = x - ox, y - oy
        length2 = dx * dx + dy * dy
        if length2 <= 0:
            return
        w, h = layer.image.size
        ys, xs = np.mgrid[0:h, 0:w]
        t = ((xs - ox) * dx + (ys - oy) * dy) / length2
        t = np.clip(t, 0.0, 1.0).astype(np.float32)
        c1 = np.array(self.ctx.primary_color, dtype=np.float32)
        c2 = np.array(self.ctx.secondary_color, dtype=np.float32)
        out = c1 * (1 - t)[..., None] + c2 * t[..., None]
        out = np.clip(out, 0, 255).astype(np.uint8)
        grad = Image.fromarray(out, mode="RGBA")
        sel_mask = _selection_at_layer(self.ctx, layer)
        if sel_mask is not None:
            grad_alpha = grad.split()[3]
            grad.putalpha(ImageChops.multiply(grad_alpha, sel_mask))
        layer.image.alpha_composite(grad)


TOOL_CLASS = GradientTool
