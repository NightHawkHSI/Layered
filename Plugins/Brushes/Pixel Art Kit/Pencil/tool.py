"""Pixel Pencil — hard, aliased single-pixel-perfect brush.

Always hardness 1.0, spacing 1px, opacity 1.0. Size = pixel diameter.
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

Tool                    = _sh.Tool
_brush_mask             = _sh._brush_mask
_stamp_color            = _sh._stamp_color
_walk                   = _sh._walk
build_brush_settings_ui = _sh.build_brush_settings_ui


class PixelPencilTool(Tool):
    name      = "Pixel Pencil"
    tool_id   = "pixel_pencil"
    icon      = "✏"
    shortcut  = "N"
    group     = "Pixel Art Kit"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size     = 1
        self.brush_hardness = 1.0
        self.brush_opacity  = 1.0
        self.brush_spacing  = 1.0

        self._last_pt = None
        self._mask_cache = None
        self._mask_cache_size = None

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent, fields=("size",))

    def _get_mask(self):
        if self.brush_size != self._mask_cache_size:
            self._mask_cache = _brush_mask(self.brush_size, 1.0)
            self._mask_cache_size = self.brush_size
        return self._mask_cache

    def _stamp(self, layer, x, y):
        _stamp_color(
            layer, int(x), int(y),
            self.ctx.primary_color, self._get_mask(),
            1.0, ctx=self.ctx,
        )

    def press(self, layer, x, y):
        self._last_pt = (int(x), int(y))
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (int(x), int(y))
            return
        for px, py in _walk(self._last_pt, (int(x), int(y)), 1.0):
            self._stamp(layer, px, py)
        self._last_pt = (int(x), int(y))

    def release(self, layer, x, y):
        self.move(layer, x, y)
        self._last_pt = None

    def cancel(self):
        self._last_pt = None


TOOL_CLASS = PixelPencilTool
