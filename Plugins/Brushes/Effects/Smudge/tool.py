import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
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
_brush_mask = _sh._brush_mask
_selection_at_layer = _sh._selection_at_layer


class SmudgeTool(Tool):
    """Pull the pixels at the previous sample point along the stroke direction."""
    name = "Smudge"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        size = self.ctx.brush_size
        r = size // 2
        sx, sy = self._last_pt
        sx0 = max(sx - r, 0); sy0 = max(sy - r, 0)
        sx1 = min(sx - r + size, layer.image.width)
        sy1 = min(sy - r + size, layer.image.height)
        if sx1 <= sx0 or sy1 <= sy0:
            self._last_pt = (x, y)
            return
        sample = layer.image.crop((sx0, sy0, sx1, sy1))
        mask = _brush_mask(sx1 - sx0, self.ctx.brush_hardness)
        opa = max(0.05, min(1.0, self.ctx.brush_opacity * 0.4))
        m = mask.point(lambda v: int(v * opa))
        sel_mask = _selection_at_layer(self.ctx, layer)
        dx = x - r; dy = y - r
        if sel_mask is not None:
            sx_clip0 = max(dx, 0); sy_clip0 = max(dy, 0)
            sx_clip1 = min(dx + (sx1 - sx0), sel_mask.size[0])
            sy_clip1 = min(dy + (sy1 - sy0), sel_mask.size[1])
            if sx_clip1 > sx_clip0 and sy_clip1 > sy_clip0:
                pad = Image.new("L", m.size, 0)
                sub = sel_mask.crop((sx_clip0, sy_clip0, sx_clip1, sy_clip1))
                pad.paste(sub, (sx_clip0 - dx, sy_clip0 - dy))
                m = ImageChops.multiply(m, pad)
        sample.putalpha(m)
        layer.image.alpha_composite(sample, dest=(dx, dy))
        self._last_pt = (x, y)

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField
        host = QWidget(parent)
        row = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)
        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px;")
            return l
        row.addWidget(lbl('Size'))
        s = SliderField(1, 500, max(1, int(ctx.brush_size)), slider_width=100)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(s)
        row.addWidget(lbl('Hardness'))
        s = SliderField(0, 100, max(0, int(ctx.brush_hardness * 100)), slider_width=90)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_hardness', v / 100.0))
        row.addWidget(s)
        row.addWidget(lbl('Opacity'))
        s = SliderField(0, 100, max(0, int(ctx.brush_opacity * 100)), slider_width=90)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_opacity', v / 100.0))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = SmudgeTool
