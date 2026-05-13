"""Soft Round brush — 0% hardness, pressure-opacity.

For soft shading, glows, gradients. Pressure source order:
  1. ctx.pressure (tablet-aware host, if present)
  2. velocity fallback: slow stroke = high opacity, fast = low

User opacity slider acts as the upper cap.
"""
import importlib.util as _iu, sys as _sys
import time
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


# Velocity → pressure mapping (canvas px / second)
_VEL_SLOW = 50.0    # at/below = full pressure
_VEL_FAST = 1500.0  # at/above = min pressure
_PRESS_MIN = 0.15


class SoftRoundTool(Tool):
    name      = "Soft Round"
    tool_id   = "soft_round"
    icon      = "◯"
    shortcut  = "Shift+S"
    group     = "Basic"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size     = 40
        self.brush_hardness = 0.0
        self.brush_opacity  = 1.0
        self.brush_spacing  = 0.05

        self._last_pt = None
        self._last_t  = None
        self._mask_cache = None
        self._mask_cache_size = None

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent, fields=("size", "opacity", "spacing"))

    def _get_mask(self):
        if self.brush_size != self._mask_cache_size:
            self._mask_cache = _brush_mask(self.brush_size, 0.0)
            self._mask_cache_size = self.brush_size
        return self._mask_cache

    def _pressure(self, x, y, now):
        p = getattr(self.ctx, "pressure", None)
        if p is not None:
            return max(_PRESS_MIN, min(1.0, float(p)))
        if self._last_pt is None or self._last_t is None:
            return 1.0
        dt = max(1e-3, now - self._last_t)
        dx = x - self._last_pt[0]; dy = y - self._last_pt[1]
        speed = (dx * dx + dy * dy) ** 0.5 / dt
        if speed <= _VEL_SLOW: return 1.0
        if speed >= _VEL_FAST: return _PRESS_MIN
        t = (speed - _VEL_SLOW) / (_VEL_FAST - _VEL_SLOW)
        return max(_PRESS_MIN, 1.0 - t * (1.0 - _PRESS_MIN))

    def _stamp(self, layer, x, y, opacity):
        _stamp_color(
            layer, x, y, self.ctx.primary_color,
            self._get_mask(), opacity, ctx=self.ctx,
        )

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._last_t  = time.monotonic()
        self._stamp(layer, x, y, self.brush_opacity)

    def move(self, layer, x, y):
        now = time.monotonic()
        if self._last_pt is None:
            self._last_pt = (x, y); self._last_t = now; return
        p = self._pressure(x, y, now)
        op = self.brush_opacity * p
        spacing = max(1.0, self.brush_size * self.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py, op)
        self._last_pt = (x, y)
        self._last_t  = now

    def release(self, layer, x, y):
        self.move(layer, x, y)
        self._last_pt = None
        self._last_t  = None

    def cancel(self):
        self._last_pt = None
        self._last_t  = None


TOOL_CLASS = SoftRoundTool
