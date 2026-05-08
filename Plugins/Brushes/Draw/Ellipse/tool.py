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

Layer = _sh.Layer
ImageDraw = _sh.ImageDraw
_ShapeTool = _sh._ShapeTool


class EllipseTool(_ShapeTool):
    name = "Ellipse"

    def _draw(self, layer: Layer, bbox: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = bbox
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.ellipse([x0, y0, x1, y1], fill=self.ctx.primary_color,
                      outline=self.ctx.primary_color, width=self.ctx.brush_size)
        else:
            d.ellipse([x0, y0, x1, y1], outline=self.ctx.primary_color,
                      width=self.ctx.brush_size)

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
        s = SliderField(1, 200, max(1, int(ctx.brush_size)), slider_width=120)
        s.valueChanged.connect(lambda v: setattr(ctx, 'brush_size', int(v)))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = EllipseTool
