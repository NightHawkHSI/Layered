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
# TOOL: Advanced Lightning / Electric Arc Brush (Fixed)
# —————————————————————————————————————————————————————————————————————————————

class LightningBrushTool(Tool):

    name = "Lightning"
    icon = "⚡"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Structure
        self.reach        = 120
        self.branches     = 3
        self.fork_chance  = 25  
        self.spread_deg   = 40
        
        # Visuals
        self.chaos        = 50
        self.glow_radius  = 5.0
        self.core_width   = 2
        
        # Internals
        self._last_pt: tuple[int, int] | None = None
        self._stroke_angle: float = -math.pi / 2

    # —————————————————————————————————————————————————————————————————————————
    # UI
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Lightning Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(165)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("reach",       "Reach (px)",    20,  500, False),
            ("branches",    "Complexity",     1,    6, False),
            ("fork_chance", "Fork Chance %",  0,  100, False),
            ("spread_deg",  "Spread Angle",   5,  360, False),
            ("chaos",       "Jaggedness",     0,  200, False),
            ("glow_radius", "Glow Size",      0,   80, True),
            ("core_width",  "Core Thickness", 1,   10, False),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 1000, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        for i, (attr, label, lo, hi, is_float) in enumerate(SLIDERS):
            grid.addWidget(lbl(label), i + 1, 0)
            val = getattr(self, attr)
            if is_float: val = int(val * 10)
            s = SliderField(lo, hi, val, slider_width=110)
            def make_h(a, f):
                return lambda v: setattr(self, a, v / 10.0 if f else int(v))
            s.valueChanged.connect(make_h(attr, is_float))
            grid.addWidget(s, i + 1, 1)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(panel)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn

    def _spacing(self):
        # Spacing to keep performance smooth
        return max(15.0, self.reach * 0.4)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stroke_angle = -math.pi / 2 # Default
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None: return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        
        # Update direction based on stroke travel
        if (dx*dx + dy*dy) > 4:
            self._stroke_angle = math.atan2(dy, dx)
            
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        alpha = int(255 * self.ctx.brush_opacity)
        p_col = self.ctx.primary_color
        r, g, b = p_col[:3]

        # DERIVE CORE COLOR: Make a "Hot" version of the selected color
        # We increase value and decrease saturation to make it look like plasma
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        core_rgb = [int(c * 255) for c in colorsys.hsv_to_rgb(h, s * 0.3, 1.0)]

        # ROBUST BOUNDING BOX
        # Chaos can make lightning wider than reach, so we pad generously
        # and don't manually clip the bx0/by0 to 0 yet.
        pad = int(self.reach + self.glow_radius + 40)
        full_dim = pad * 2
        bx0, by0 = (cx - ox - pad), (cy - oy - pad)
        
        # Create unclipped scratch canvases
        scratch_glow = Image.new("RGBA", (full_dim, full_dim), (0, 0, 0, 0))
        scratch_core = Image.new("RGBA", (full_dim, full_dim), (0, 0, 0, 0))
        d_glow = ImageDraw.Draw(scratch_glow)
        d_core = ImageDraw.Draw(scratch_core)

        # Center in scratch space
        scx, scy = pad, pad

        # Burst count scales with brush size
        num_bolts = max(1, self.ctx.brush_size // 20)
        half_spread = math.radians(self.spread_deg) / 2.0

        for _ in range(num_bolts):
            angle = self._stroke_angle + random.uniform(-half_spread, half_spread)
            
            self._draw_bolt(
                d_glow, d_core,
                scx, scy,
                angle,
                self.reach,
                alpha,
                (r, g, b),
                tuple(core_rgb),
                0
            )

        # Apply Bloom
        if self.glow_radius > 0:
            scratch_glow = scratch_glow.filter(ImageFilter.GaussianBlur(self.glow_radius))

        # Final Composite (PIL handles negative dest automatically)
        layer.image.alpha_composite(scratch_glow, dest=(int(bx0), int(by0)))
        layer.image.alpha_composite(scratch_core, dest=(int(bx0), int(by0)))

    def _draw_bolt(self, d_glow, d_core, x, y, angle, length, alpha, glow_rgb, core_rgb, depth):
        if length < 5 or alpha < 10 or depth > self.branches:
            return

        segs = max(4, int(length / 5))
        seg_len = length / segs
        chaos_rad = (self.chaos / 100.0) * 0.9
        
        px, py = x, y
        cur_angle = angle

        for i in range(segs):
            # Path logic
            cur_angle += random.uniform(-chaos_rad, chaos_rad)
            nx = px + math.cos(cur_angle) * seg_len
            ny = py + math.sin(cur_angle) * seg_len
            
            # Fade towards tip
            t = i / segs
            seg_alpha = int(alpha * (1.0 - (t * 0.4)))
            
            # Glow Pass
            glow_w = self.core_width + 4 + (depth * 2)
            d_glow.line([(px, py), (nx, ny)], fill=glow_rgb + (seg_alpha // 3,), width=glow_w)
            
            # Plasma Core Pass
            core_w = max(1, self.core_width - depth)
            d_core.line([(px, py), (nx, ny)], fill=core_rgb + (seg_alpha,), width=core_w)

            # Recursive forking
            if random.random() * 100 < self.fork_chance:
                fork_angle = cur_angle + random.uniform(0.3, 1.0) * random.choice([-1, 1])
                self._draw_bolt(
                    d_glow, d_core,
                    nx, ny,
                    fork_angle,
                    length * random.uniform(0.4, 0.7),
                    int(seg_alpha * 0.7),
                    glow_rgb, core_rgb,
                    depth + 1
                )

            px, py = nx, ny

TOOL_CLASS = LightningBrushTool