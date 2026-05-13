"""Hard Round brush — 100% hardness, fixed size.

For blocking in shapes and UI outlines. Crisp aliased edges.
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


class HardRoundTool(Tool):
    name      = "Hard Round"
    tool_id   = "hard_round"
    icon      = "●"
    shortcut  = "Shift+H"
    group     = "Basic"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size     = 20
        self.brush_hardness = 1.0
        self.brush_opacity  = 1.0
        self.brush_spacing  = 0.05

        self._last_pt = None
        self._mask_cache = None
        self._mask_cache_size = None

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent, fields=("size", "opacity", "spacing"))

    def _get_mask(self):
        if self.brush_size != self._mask_cache_size:
            self._mask_cache = _brush_mask(self.brush_size, 1.0)
            self._mask_cache_size = self.brush_size
        return self._mask_cache

    def _stamp(self, layer, x, y):
        _stamp_color(
            layer, x, y, self.ctx.primary_color,
            self._get_mask(), self.brush_opacity, ctx=self.ctx,
        )

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y); return
        spacing = max(1.0, self.brush_size * self.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer, x, y):
        self.move(layer, x, y)
        self._last_pt = None

    def cancel(self):
        self._last_pt = None


TOOL_CLASS = HardRoundTool
