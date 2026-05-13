"""Chisel / Flat brush — rectangular hard-edged stamp.

For architectural assets, UI elements, painterly block-ins.
Width / height / angle adjustable. Angle in degrees (0 = horizontal).
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
Image                   = _sh.Image
ImageDraw               = _sh.ImageDraw
_stamp_color            = _sh._stamp_color
_walk                   = _sh._walk
SliderField             = _sh.SliderField
QWidget                 = _sh.QWidget
QHBoxLayout             = _sh.QHBoxLayout
QLabel                  = _sh.QLabel
math                    = _sh.math


def _flat_mask(width: int, height: int, angle_deg: float):
    """Build a rotated rectangular L-mode mask centred in a square canvas."""
    width  = max(1, int(width))
    height = max(1, int(height))
    diag = int(math.ceil(math.hypot(width, height))) + 2
    if diag % 2 == 0:
        diag += 1
    mask = Image.new("L", (diag, diag), 0)
    draw = ImageDraw.Draw(mask)
    cx = cy = diag / 2.0
    x0 = cx - width / 2.0
    y0 = cy - height / 2.0
    x1 = cx + width / 2.0
    y1 = cy + height / 2.0
    if abs(angle_deg) < 0.5:
        draw.rectangle((x0, y0, x1, y1), fill=255)
        return mask
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    rotated = []
    for px, py in corners:
        rx = cx + (px - cx) * cos_a - (py - cy) * sin_a
        ry = cy + (px - cx) * sin_a + (py - cy) * cos_a
        rotated.append((rx, ry))
    draw.polygon(rotated, fill=255)
    return mask


class ChiselFlatTool(Tool):
    name      = "Chisel Flat"
    tool_id   = "chisel_flat"
    icon      = "▬"
    shortcut  = "Shift+C"
    group     = "Basic"
    commit_on = "release"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_width   = 40
        self.brush_height  = 10
        self.brush_angle   = 30.0
        self.brush_opacity = 1.0
        self.brush_spacing = 0.05

        self._last_pt = None
        self._mask_cache = None
        self._mask_key = None

    def build_ui(self, parent, ctx):
        w = QWidget(parent)
        w.setFixedHeight(28)
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        row.addWidget(QLabel("W"))
        sw = SliderField(1, 300, int(self.brush_width))
        sw.setMinimumWidth(110)
        sw.valueChanged.connect(lambda v: setattr(self, "brush_width", int(v)) or self._invalidate())
        row.addWidget(sw)

        row.addWidget(QLabel("H"))
        sh = SliderField(1, 300, int(self.brush_height))
        sh.setMinimumWidth(110)
        sh.valueChanged.connect(lambda v: setattr(self, "brush_height", int(v)) or self._invalidate())
        row.addWidget(sh)

        row.addWidget(QLabel("Angle"))
        sa = SliderField(0, 359, int(self.brush_angle), suffix="°")
        sa.setMinimumWidth(110)
        sa.valueChanged.connect(lambda v: setattr(self, "brush_angle", float(v)) or self._invalidate())
        row.addWidget(sa)

        row.addWidget(QLabel("Opacity"))
        so = SliderField(1, 100, int(self.brush_opacity * 100), suffix="%")
        so.setMinimumWidth(110)
        so.valueChanged.connect(lambda v: setattr(self, "brush_opacity", v / 100.0))
        row.addWidget(so)

        row.addStretch(1)
        return w

    def _invalidate(self):
        self._mask_cache = None
        self._mask_key = None

    def _get_mask(self):
        key = (self.brush_width, self.brush_height, round(self.brush_angle, 1))
        if key != self._mask_key:
            self._mask_cache = _flat_mask(self.brush_width, self.brush_height, self.brush_angle)
            self._mask_key = key
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
        step = max(self.brush_width, self.brush_height)
        spacing = max(1.0, step * self.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer, x, y):
        self.move(layer, x, y)
        self._last_pt = None

    def cancel(self):
        self._last_pt = None


TOOL_CLASS = ChiselFlatTool
