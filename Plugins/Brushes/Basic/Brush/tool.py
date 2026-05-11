import importlib.util as _iu, sys as _sys
from pathlib import Path as _P

# -------------------------------------------------------------------------
# Shared imports loader
# -------------------------------------------------------------------------

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


# -------------------------------------------------------------------------
# Brush Tool
# -------------------------------------------------------------------------

class BrushTool(Tool):
    name       = "Brush"
    tool_id    = "brush"
    icon       = "🖌"
    shortcut   = "B"
    group      = "Basic"
    is_default = True
    commit_on  = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)

        self.brush_size = 20
        self.brush_hardness = 0.8
        self.brush_opacity = 1.0
        self.brush_spacing = 0.05

        self._last_pt = None
        self._mask_cache = None
        self._mask_cache_key = None

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(
            self,
            parent,
            fields=("size", "hardness", "opacity", "spacing"),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_mask(self):
        key = (self.brush_size, self.brush_hardness)

        if key != self._mask_cache_key:
            self._mask_cache = _brush_mask(
                self.brush_size,
                self.brush_hardness,
            )
            self._mask_cache_key = key

        return self._mask_cache

    def _stamp(self, layer, x, y):
        _stamp_color(
            layer,
            x,
            y,
            self.ctx.primary_color,
            self._get_mask(),
            self.brush_opacity,
            ctx=self.ctx,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y)
            return

        spacing = max(
            1.0,
            self.brush_size * self.brush_spacing,
        )

        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py)

        self._last_pt = (x, y)

    def release(self, layer, x, y):
        self.move(layer, x, y)
        self._last_pt = None

    def cancel(self):
        self._last_pt = None


# -------------------------------------------------------------------------
# Required export
# -------------------------------------------------------------------------

TOOL_CLASS = BrushTool