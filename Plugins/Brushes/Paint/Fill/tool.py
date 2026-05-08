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
ImageDraw = _sh.ImageDraw
_clip_layer_to_selection = _sh._clip_layer_to_selection
_selection_at_layer = _sh._selection_at_layer


class FillTool(Tool):
    name = "Fill"
    commit_on = "press"

    def press(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        lx, ly = x - ox, y - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return
        before = layer.image.copy()
        if self.ctx.ctrl_held:
            rgba = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
            fill = Image.new("RGBA", rgba.size, self.ctx.primary_color)
            sel_mask = _selection_at_layer(self.ctx, layer)
            if sel_mask is not None:
                rgba.paste(fill, mask=sel_mask)
            else:
                rgba.paste(fill)
            layer.image = rgba
        else:
            rgba = layer.image
            target = rgba.getpixel((lx, ly))
            replacement = self.ctx.primary_color
            if target == replacement:
                return
            ImageDraw.floodfill(rgba, (lx, ly), replacement, thresh=self.ctx.fill_tolerance)
            _clip_layer_to_selection(layer, self.ctx, before)

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
        row.addWidget(lbl('Tolerance'))
        s = SliderField(0, 255, max(0, int(ctx.fill_tolerance)), slider_width=120)
        s.valueChanged.connect(lambda v: setattr(ctx, 'fill_tolerance', int(v)))
        row.addWidget(s)
        row.addStretch()
        return host


TOOL_CLASS = FillTool
