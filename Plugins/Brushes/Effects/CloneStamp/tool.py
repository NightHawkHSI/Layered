import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
from typing import Optional
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
ToolContext = _sh.ToolContext
_brush_mask = _sh._brush_mask
_selection_at_layer = _sh._selection_at_layer
_walk = _sh._walk


class CloneStampTool(Tool):
    """Alt-click sets a source point; subsequent drags stamp the source pixels."""
    name = "Clone Stamp"

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._source: Optional[tuple[int, int]] = None
        self._delta: Optional[tuple[int, int]] = None
        self._last_pt: Optional[tuple[int, int]] = None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self.ctx.alt_held:
            self._source = (x, y)
            return
        if self._source is None:
            return
        self._delta = (self._source[0] - x, self._source[1] - y)
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._source is None or self._delta is None or self._last_pt is None:
            return
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = None
        super().release(layer, x, y)

    def _stamp(self, layer: Layer, x: int, y: int) -> None:
        if self._delta is None:
            return
        dx, dy = self._delta
        size = self.ctx.brush_size
        r = size // 2
        sx, sy = x + dx, y + dy
        sx0 = max(sx - r, 0); sy0 = max(sy - r, 0)
        sx1 = min(sx - r + size, layer.image.width)
        sy1 = min(sy - r + size, layer.image.height)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        sample = layer.image.crop((sx0, sy0, sx1, sy1))
        mw, mh = sx1 - sx0, sy1 - sy0
        mask = _brush_mask(size, self.ctx.brush_hardness)
        mx0 = sx0 - (sx - r); my0 = sy0 - (sy - r)
        sub_mask = mask.crop((mx0, my0, mx0 + mw, my0 + mh))
        sub_mask = sub_mask.point(lambda v: int(v * self.ctx.brush_opacity))
        sel_mask = _selection_at_layer(self.ctx, layer)
        if sel_mask is not None:
            tgt_x = x - r + (sx0 - (sx - r))
            tgt_y = y - r + (sy0 - (sy - r))
            tgt_x0 = max(tgt_x, 0); tgt_y0 = max(tgt_y, 0)
            tgt_x1 = min(tgt_x + mw, sel_mask.size[0])
            tgt_y1 = min(tgt_y + mh, sel_mask.size[1])
            pad = Image.new("L", (mw, mh), 0)
            if tgt_x1 > tgt_x0 and tgt_y1 > tgt_y0:
                sub = sel_mask.crop((tgt_x0, tgt_y0, tgt_x1, tgt_y1))
                pad.paste(sub, (tgt_x0 - tgt_x, tgt_y0 - tgt_y))
            sub_mask = ImageChops.multiply(sub_mask, pad)
        sample.putalpha(sub_mask)
        target_x = x - r + (sx0 - (sx - r))
        target_y = y - r + (sy0 - (sy - r))
        layer.image.alpha_composite(sample, dest=(target_x, target_y))

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
        row.addWidget(lbl('Spacing'))
        s = SliderField(0, 100, max(0, int(ctx.brush_spacing * 100)), slider_width=90)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_spacing', v / 100.0))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = CloneStampTool
