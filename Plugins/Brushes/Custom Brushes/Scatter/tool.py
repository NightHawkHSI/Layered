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
# TOOL: Pro Scatter Brush
# —————————————————————————————————————————————————————————————————————————————

class ScatterBrushTool(Tool):

    name = "Scatter"
    icon = "✿"

    def __init__(self, ctx=None):
        super().__init__(ctx)

        # Cluster Distribution
        self.density        = 10
        self.spread_pct     = 150
        self.center_bias    = 8.0  # 1.0 = even, >1.0 = clumped at center
        
        # Shape & Size
        self.shape_type     = 0    # 0: Circle, 1: Square, 2: Star
        self.min_dot_size   = 2
        self.max_dot_size   = 8
        self.rotation_jit   = 100  # % random rotation
        
        # Jitters
        self.size_jitter    = 50   # %
        self.opacity_jitter = 40   # %
        self.hue_jitter     = 5    # %
        self.sat_val_jitter = 20   # % variation in saturation/brightness
        
        # Rendering
        self.softness       = 0.0
        self.glow_radius    = 0
        self.spacing_mult   = 1.0

        self._last_pt = None
        self._stroke_angle = 0.0

    # —————————————————————————————————————————————————————————————————————————
    # UI (Popup Grid Layout)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Scatter Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(160)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        # (attr, label, lo, hi, width, is_float)
        SLIDERS = [
            ("density",        "Density",        1,   60, 110, False),
            ("spread_pct",     "Spread %",      10,  800, 110, False),
            ("center_bias",    "Clumping",       1,  100, 110, True),
            ("shape_type",     "Shape (0-2)",    0,    2, 110, False),
            ("min_dot_size",   "Min Size",       1,   30, 110, False),
            ("max_dot_size",   "Max Size",       1,   80, 110, False),
            ("rotation_jit",   "Rotate Jitter",  0,  100, 110, False),
            ("size_jitter",    "Size Jitter",    0,  100, 110, False),
            ("hue_jitter",     "Color Jitter",   0,  100, 110, False),
            ("sat_val_jitter", "Dynamic Range",  0,  100, 110, False),
            ("glow_radius",    "Glow",           0,   20, 110, False),
            ("spacing_mult",   "Spacing",        5,  100, 110, True),
            ("softness",       "Softness",       0,   50, 110, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 800, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        for i, (attr, label, lo, hi, width, is_float) in enumerate(SLIDERS):
            grid.addWidget(lbl(label), i+1, 0)
            current = getattr(self, attr)
            if is_float: current = int(current * 10)
            s = SliderField(lo, hi, current, slider_width=width)
            def make_handler(a, f_mode):
                return lambda v: setattr(self, a, v / 10.0 if f_mode else int(v))
            s.valueChanged.connect(make_handler(attr, is_float))
            grid.addWidget(s, i+1, 1)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(panel)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn

    # —————————————————————————————————————————————————————————————————————————
    # Stroke Logic
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        return max(2.0, self.ctx.brush_size * self.ctx.brush_spacing * self.spacing_mult)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        if (dx*dx + dy*dy) > 1:
            self._stroke_angle = math.atan2(dy, dx)
            
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        br = max(1, int(self.ctx.brush_size // 2))
        spread_r = max(1, int(br * self.spread_pct / 100))
        
        r, g, b = self.ctx.primary_color[:3]
        base_alpha = int(255 * self.ctx.brush_opacity)
        
        # Calculate Bounding Box
        pad = int(self.max_dot_size + self.softness + self.glow_radius + 10)
        bx0, by0 = max(0, cx - ox - spread_r - pad), max(0, cy - oy - spread_r - pad)
        bx1, by1 = min(layer.image.width, cx - ox + spread_r + pad), min(layer.image.height, cy - oy + spread_r + pad)
        
        bw, bh = int(bx1 - bx0), int(by1 - by0)
        if bw <= 0 or bh <= 0: return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        
        h_base, s_base, v_base = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        s_min, s_max = sorted([self.min_dot_size, self.max_dot_size])

        for _ in range(max(1, self.density)):
            # 1. Distribution (Center Bias)
            angle = random.uniform(0, 2 * math.pi)
            dist = (random.random() ** (self.center_bias / 10.0)) * spread_r
            lx = (cx - ox - bx0) + dist * math.cos(angle)
            ly = (cy - oy - by0) + dist * math.sin(angle)
            
            # 2. Size & Rotation
            dot_r = random.uniform(s_min, s_max)
            if self.size_jitter > 0:
                dot_r *= (1.0 - random.random() * (self.size_jitter / 100.0))
            
            rot = math.degrees(self._stroke_angle) + random.uniform(-180, 180) * (self.rotation_jit / 100.0)
            
            # 3. Color Dynamics
            alpha = base_alpha
            if self.opacity_jitter > 0:
                alpha = int(alpha * (1.0 - random.random() * (self.opacity_jitter / 100.0)))
            
            h, s, v = h_base, s_base, v_base
            if self.hue_jitter > 0:
                h = (h + (random.random() - 0.5) * (self.hue_jitter / 50.0)) % 1.0
            if self.sat_val_jitter > 0:
                s = max(0, min(1, s + (random.random() - 0.5) * (self.sat_val_jitter / 50.0)))
                v = max(0, min(1, v + (random.random() - 0.5) * (self.sat_val_jitter / 50.0)))
            
            fill_color = tuple([int(c*255) for c in colorsys.hsv_to_rgb(h, s, v)]) + (alpha,)

            # 4. Draw Glow
            if self.glow_radius > 0:
                glow_a = alpha // 6
                glow_color = fill_color[:3] + (glow_a,)
                gr = dot_r + self.glow_radius
                draw.ellipse([lx-gr, ly-gr, lx+gr, ly+gr], fill=glow_color)

            # 5. Draw Shape
            if self.shape_type == 0: # Circle
                draw.ellipse([lx-dot_r, ly-dot_r, lx+dot_r, ly+dot_r], fill=fill_color)
            elif self.shape_type == 1: # Square
                # Simple rotated square
                points = []
                for a in [45, 135, 225, 315]:
                    rad = math.radians(a + rot)
                    points.append((lx + dot_r * 1.4 * math.cos(rad), ly + dot_r * 1.4 * math.sin(rad)))
                draw.polygon(points, fill=fill_color)
            else: # Star
                points = []
                for i in range(10):
                    a = math.radians(i * 36 + rot)
                    r_val = dot_r * (1.0 if i % 2 == 0 else 0.4)
                    points.append((lx + r_val * math.cos(a), ly + r_val * math.sin(a)))
                draw.polygon(points, fill=fill_color)

        # 6. Post-Process
        if self.softness > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.softness))

        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

TOOL_CLASS = ScatterBrushTool