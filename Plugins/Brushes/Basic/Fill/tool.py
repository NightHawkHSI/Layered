"""Fill (paint bucket) tool.

Click a pixel — flood-fills connected region of similar colour with the
primary colour. Tolerance slider controls similarity threshold (0-255).
Selection-aware: result is clipped to the active selection.
"""
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

Tool                      = _sh.Tool
ImageDraw                 = _sh.ImageDraw
_clip_layer_to_selection  = _sh._clip_layer_to_selection
build_brush_settings_ui   = _sh.build_brush_settings_ui


class FillTool(Tool):
    name      = "Fill"
    tool_id   = "fill"
    icon      = "🪣"
    shortcut  = "F"
    group     = "Basic"
    commit_on = "press"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.tolerance = 32

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent, fields=("tolerance",))

    def press(self, layer, x, y):
        ox, oy = layer.offset
        lx, ly = int(x) - ox, int(y) - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return

        img = layer.image
        target = img.getpixel((lx, ly))
        replacement = self.ctx.primary_color
        if target == replacement:
            return

        before = img.copy()
        ImageDraw.floodfill(img, (lx, ly), replacement, thresh=int(self.tolerance))
        _clip_layer_to_selection(layer, self.ctx, before)


TOOL_CLASS = FillTool
