import importlib.util
import math
import sys
import random
import colorsys

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

from app.layer import Layer
from app.tools import Tool

# —————————————————————————————————————————————————————————————————————————————
# load shared builtins
# —————————————————————————————————————————————————————————————————————————————

_K = "_layered_brushes_shared"

if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[2] / "_shared.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)

_bt   = sys.modules[_K]
_walk = _bt._walk

# —————————————————————————————————————————————————————————————————————————————
# TOOL: Professional Spray Brush
# —————————————————————————————————————————————————————————————————————————————

class SprayBrushTool(Tool):

    name = "Spray"
    icon = "💨"

    def __init__(self, ctx=None):
        super().__init__(ctx)

        # Flow & Density
        self.density        = 15
        self.spread_pct     = 100
        
        # Cap / Nozzle settings
        self.droplet_size   = 1.5   # stored as tenths
        self.softness       = 0.5   # stored as tenths
        
        # Variation
        self.hue_jitter     = 2
        self.spacing_mult   = 0.5
        self.opacity_jitter = 20

    # —————————————————————————————————————————————————————————————————————————
    # UI (Constellation Style)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Spray Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(160)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        # (attr, label, lo, hi, width, is_float)
        SLIDERS = [
            ("density",        "Flow/Density",   1,   100, 110, False),
            ("spread_pct",     "Spread %",      10,   500, 110, False),
            ("droplet_size",   "Drop Size",      5,   100, 110, True),
            ("softness",       "Softness",       0,    50, 110, True),
            ("opacity_jitter", "Opacity Var",    0,   100, 110, False),
            ("hue_jitter",     "Color Var",      0,   100, 110, False),
            ("spacing_mult",   "Spacing",        1,    50, 110, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        # Standard context controls
        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 800, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        grid.addWidget(lbl("Brush Opacity"), 1, 0)
        s_opac = SliderField(1, 100, max(1, int(ctx.brush_opacity)), slider_width=110)
        s_opac.valueChanged.connect(lambda v: setattr(ctx, "brush_opacity", int(v)))
        grid.addWidget(s_opac, 1, 1)

        OFFSET = 2
        for i, (attr, label, lo, hi, width, is_float) in enumerate(SLIDERS):
            row, col = divmod(i, 2)
            row += OFFSET
            grid.addWidget(lbl(label), row, col * 2)

            current = getattr(self, attr)
            if is_float: current = int(current * 10)

            s = SliderField(lo, hi, current, slider_width=width)

            def make_handler(a, f_mode):
                def _h(v):
                    setattr(self, a, v / 10.0 if f_mode else int(v))
                return _h

            s.valueChanged.connect(make_handler(attr, is_float))
            grid.addWidget(s, row, col * 2 + 1)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(panel)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn

    # —————————————————————————————————————————————————————————————————————————
    # Stroke Logic
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        return max(1.5, self.ctx.brush_size * 0.1 * self.spacing_mult)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        br = max(1, self.ctx.brush_size // 2)
        spread_r = max(1, int(br * self.spread_pct / 100))
        
        r, g, b = self.ctx.primary_color[:3]
        base_alpha = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        
        # Scratch canvas sizing
        pad = int(self.droplet_size + self.softness + 4)
        bx0, by0 = max(0, cx - ox - spread_r - pad), max(0, cy - oy - spread_r - pad)
        bx1, by1 = min(layer.image.width, cx - ox + spread_r + pad), min(layer.image.height, cy - oy + spread_r + pad)
        
        bw, bh = bx1 - bx0, by1 - by0
        if bw <= 0 or bh <= 0: return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        
        h_base, s_base, v_base = colorsys.rgb_to_hsv(r/255, g/255, b/255)

        for _ in range(max(1, self.density)):
            # Real spray is denser in the center (Gaussian-ish distribution)
            angle = random.uniform(0, 2 * math.pi)
            dist = (random.random() ** 1.5) * spread_r # Square power for center-bias
            
            lx = (cx - ox - bx0) + dist * math.cos(angle)
            ly = (cy - oy - by0) + dist * math.sin(angle)
            
            # Droplet properties
            ds = max(0.5, self.droplet_size * random.uniform(0.7, 1.3))
            
            alpha = base_alpha
            if self.opacity_jitter > 0:
                alpha = int(alpha * (1.0 - random.random() * (self.opacity_jitter / 100.0)))
            
            if self.hue_jitter > 0:
                h_off = (random.random() - 0.5) * (self.hue_jitter / 100.0)
                nr, ng, nb = colorsys.hsv_to_rgb((h_base + h_off) % 1.0, s_base, v_base)
                fill_color = (int(nr*255), int(ng*255), int(nb*255), alpha)
            else:
                fill_color = (r, g, b, alpha)

            # Draw droplet
            if ds < 1.2 and self.softness < 0.2:
                # Use faster point for very fine dry spray
                draw.point((int(lx), int(ly)), fill=fill_color)
            else:
                draw.ellipse([lx-ds, ly-ds, lx+ds, ly+ds], fill=fill_color)

        # Apply soft airbrush filtering
        if self.softness > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.softness))

        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

TOOL_CLASS = SprayBrushTool