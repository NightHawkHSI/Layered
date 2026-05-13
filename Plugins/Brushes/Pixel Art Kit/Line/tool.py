"""Pixel Line — Bresenham line tool. Click-drag for live preview; release commits.

Shift snaps to 0/45/90 degrees.
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
_clip_layer_to_selection = _sh._clip_layer_to_selection
build_brush_settings_ui = _sh.build_brush_settings_ui
math                    = _sh.math


def _bresenham(x0, y0, x1, y1):
    """Integer Bresenham line — yields each pixel (x, y) along p0→p1."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx = abs(x1 - x0); dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


def _snap_octant(x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return x1, y1
    angle = math.degrees(math.atan2(dy, dx))
    snap  = round(angle / 45.0) * 45.0
    rad   = math.radians(snap)
    length = math.hypot(dx, dy)
    return int(round(x0 + math.cos(rad) * length)), int(round(y0 + math.sin(rad) * length))


class PixelLineTool(Tool):
    name      = "Pixel Line"
    tool_id   = "pixel_line"
    icon      = "📏"
    shortcut  = "Shift+L"
    group     = "Pixel Art Kit"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size = 1

        self._snapshot = None
        self._p0 = None
        self._p1 = None
        self._mask_cache = None
        self._mask_cache_size = None

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent, fields=("size",))

    def _get_mask(self):
        if self.brush_size != self._mask_cache_size:
            self._mask_cache = _brush_mask(self.brush_size, 1.0)
            self._mask_cache_size = self.brush_size
        return self._mask_cache

    def _draw(self, layer):
        if self._snapshot is None or self._p0 is None or self._p1 is None:
            return
        layer.image = self._snapshot.copy()
        x0, y0 = self._p0
        x1, y1 = self._p1
        if self.ctx.shift_held:
            x1, y1 = _snap_octant(x0, y0, x1, y1)
        mask  = self._get_mask()
        color = self.ctx.primary_color
        for px, py in _bresenham(x0, y0, x1, y1):
            _stamp_color(layer, px, py, color, mask, 1.0, ctx=self.ctx)
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def press(self, layer, x, y):
        self._snapshot = layer.image.copy()
        self._p0 = (int(x), int(y))
        self._p1 = (int(x), int(y))
        self._draw(layer)

    def move(self, layer, x, y):
        if self._p0 is None:
            return
        self._p1 = (int(x), int(y))
        self._draw(layer)

    def release(self, layer, x, y):
        if self._p0 is None:
            return
        self._p1 = (int(x), int(y))
        self._draw(layer)
        self._snapshot = None
        self._p0 = None
        self._p1 = None

    def cancel(self):
        self._snapshot = None
        self._p0 = None
        self._p1 = None


TOOL_CLASS = PixelLineTool
