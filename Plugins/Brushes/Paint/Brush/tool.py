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
_brush_mask = _sh._brush_mask
_stamp_color = _sh._stamp_color
_walk = _sh._walk


class BrushTool(Tool):
    name = "Brush"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color, mask, self.ctx.brush_opacity, ctx=self.ctx)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = self._spacing()
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_color(layer, px, py, self.ctx.primary_color, mask, self.ctx.brush_opacity, ctx=self.ctx)
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
        row.addWidget(lbl('Spacing'))
        s = SliderField(0, 100, max(0, int(ctx.brush_spacing * 100)), slider_width=90)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_spacing', v / 100.0))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = BrushTool
