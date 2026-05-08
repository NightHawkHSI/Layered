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
ImageDraw = _sh.ImageDraw
_clip_layer_to_selection = _sh._clip_layer_to_selection


class LineTool(Tool):
    name = "Line"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snapshot.copy()
        ImageDraw.Draw(layer.image).line(
            [self._origin, (x, y)], fill=self.ctx.primary_color, width=self.ctx.brush_size
        )
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)

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


TOOL_CLASS = LineTool
