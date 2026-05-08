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
# Load shared builtins
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
# TOOL: Constellation Brush
# —————————————————————————————————————————————————————————————————————————————

class ConstellationBrushTool(Tool):

    name = "Constellation"
    icon = "✧"

    def __init__(self, ctx=None):
        super().__init__(ctx)

        # Base generation
        self.star_count   = 6
        self.spread_pct   = 350
        self.connect_pct  = 450
        self.glow_radius  = 3

        # Star size controls
        self.min_star_size     = 1
        self.max_star_size     = 4

        # Connection lines
        self.line_width        = 1
        self.connection_alpha  = 35

        # Variation / Realism
        self.color_shift       = 20
        self.sparkle_chance    = 5
        self.big_star_chance   = 3

        # Density and Spacing
        self.density           = 100
        self.star_spacing_mult = 2.5

        # Filtering
        self.blur_strength     = 0.7

        # Neon effect
        self.neon_chance       = 8    
        self.neon_intensity    = 1.0  

        # Internal state
        self._prev_stars: list[tuple[int, int]] = []
        self._last_pt: tuple[int, int] | None = None

    # —————————————————————————————————————————————————————————————————————————
    # UI Construction
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Constellation ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(150)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        # (attribute, label, min, max, width, is_float)
        SLIDERS = [
            ("star_count",        "Star Density",   1,   25, 110, False),
            ("spread_pct",        "Cluster Size",  10, 1000, 110, False),
            ("connect_pct",       "Connect Dist",   0, 1000, 110, False),
            ("glow_radius",       "Glow Radius",    0,   15, 110, False),
            ("min_star_size",     "Min Size",       1,   10, 110, False),
            ("max_star_size",     "Max Size",       1,   25, 110, False),
            ("line_width",        "Line Width",     1,    8, 110, False),
            ("connection_alpha",  "Line Opacity",   0,  100, 110, False),
            ("color_shift",       "Color Var",      0,  100, 110, False),
            ("sparkle_chance",    "Sparkle %",      0,  100, 110, False),
            ("big_star_chance",   "Rare Star %",    0,   50, 110, False),
            ("density",           "Fill %",        10,  300, 110, False),
            ("star_spacing_mult", "Stamp Gap",      5,   80, 110, True),
            ("blur_strength",     "Softness",       1,   50, 110, True),
            ("neon_chance",       "Neon %",         0,  100, 110, False),
            ("neon_intensity",    "Neon Power",     1,   30, 110, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        # Handle Brush Size separately (stored on context)
        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 800, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        OFFSET = 1
        for i, (attr, label, lo, hi, width, is_float) in enumerate(SLIDERS):
            row, col = divmod(i, 2)
            row += OFFSET
            grid.addWidget(lbl(label), row, col * 2)

            current_val = getattr(self, attr)
            if is_float: current_val = int(current_val * 10)

            s = SliderField(lo, hi, current_val, slider_width=width)

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
        return max(4.0, self.ctx.brush_size * self.ctx.brush_spacing * self.star_spacing_mult)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._prev_stars.clear()
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return

        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)

        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._prev_stars.clear()
        super().release(layer, x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Stamp Logic
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        br = max(1, self.ctx.brush_size)
        
        # Ranges
        spread_r = max(1, int(br * self.spread_pct / 100))
        connect_r = int(br * self.connect_pct / 100)
        alpha = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        W, H = layer.image.width, layer.image.height

        # 1. Generate local cluster
        new_stars: list[tuple[int, int]] = []
        actual_count = max(1, int(self.star_count * (self.density / 100)))

        for _ in range(actual_count):
            angle = random.uniform(0, 2 * math.pi)
            dist = (random.uniform(0.0, 1.0) ** 1.8) * spread_r
            sx = int(cx - ox + dist * math.cos(angle))
            sy = int(cy - oy + dist * math.sin(angle))
            if 0 <= sx < W and 0 <= sy < H:
                new_stars.append((sx, sy))

        if not new_stars:
            return

        # 2. Find connection candidates from history
        close_prev: list[tuple[int, int]] = []
        if connect_r > 0 and self._prev_stars:
            for p in self._prev_stars:
                if any(math.hypot(nx - p[0], ny - p[1]) <= connect_r for nx, ny in new_stars):
                    close_prev.append(p)

        # 3. Calculate Scratch Canvas Bounding Box
        all_pts = new_stars + close_prev
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]

        # Calculate padding needed for glow + spikes
        max_size_allowed = max(self.min_star_size, self.max_star_size)
        pad = int(self.glow_radius * 5 + max_size_allowed + 30)

        bx0, by0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
        bx1, by1 = min(W, max(xs) + pad), min(H, max(ys) + pad)
        bw, bh = bx1 - bx0, by1 - by0

        if bw <= 0 or bh <= 0: return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scratch)

        def lc(px, py): return (px - bx0, py - by0)

        # 4. Draw Constellation Lines
        for (sx, sy) in new_stars:
            for (px, py) in close_prev:
                dist = math.hypot(sx - px, sy - py)
                if 0 < dist <= connect_r:
                    line_a = int(alpha * (self.connection_alpha / 100.0) * (1.0 - dist / connect_r))
                    if line_a < 2: continue
                    
                    p1, p2 = lc(sx, sy), lc(px, py)
                    # Outer glow of line
                    sd.line([p1, p2], fill=(r, g, b, max(1, line_a // 5)), width=self.line_width + 3)
                    # Sharp core of line
                    sd.line([p1, p2], fill=(255, 255, 255, line_a), width=self.line_width)

        # 5. Draw Stars
        s_min, s_max = sorted([self.min_star_size, self.max_star_size])

        for (sx, sy) in new_stars:
            lx, ly = lc(sx, sy)
            
            # Size and Color
            size_bias = random.uniform(0.0, 1.0) ** 2.2
            dot_r = int(s_min + (s_max - s_min) * size_bias)
            
            brightness = random.uniform(0.8, 1.4)
            shift = lambda c: max(0, min(255, int(c * brightness) + random.randint(-self.color_shift, self.color_shift)))
            sr, sg, sb = shift(r), shift(g), shift(b)

            # Atmospheric tinting
            temp = random.random()
            if temp < 0.15: # Blue-ish
                sb = min(255, sb + 40); sg = min(255, sg + 10)
            elif temp > 0.85: # Red-ish
                sr = min(255, sr + 40)

            star_alpha = int(alpha * random.uniform(0.7, 1.0))

            # Outer Glow
            g_rad = dot_r + random.randint(4, 10)
            sd.ellipse([lx-g_rad, ly-g_rad, lx+g_rad, ly+g_rad], fill=(sr, sg, sb, star_alpha // 15))

            # Core
            sd.ellipse([lx-dot_r, ly-dot_r, lx+dot_r, ly+dot_r], fill=(255, 255, 255, star_alpha))

            # Neon Effect
            if random.random() * 100 < self.neon_chance:
                nhue = random.random()
                nr, ng, nb = [int(c*255) for c in colorsys.hsv_to_rgb(nhue, 0.8, 1.0)]
                n_int = self.neon_intensity
                bloom = int(dot_r * 6 * n_int) + 5
                sd.ellipse([lx-bloom, ly-bloom, lx+bloom, ly+bloom], fill=(nr, ng, nb, star_alpha // 10))
                sd.ellipse([lx-dot_r, ly-dot_r, lx+dot_r, ly+dot_r], fill=(nr, ng, nb, star_alpha))
                sd.ellipse([lx-1, ly-1, lx+1, ly+1], fill=(255, 255, 255, star_alpha))

            # Sparkles
            if random.random() * 100 < self.sparkle_chance:
                spike = dot_r + random.randint(5, 12)
                sa = star_alpha // 2
                sd.line([lx-spike, ly, lx+spike, ly], fill=(255, 255, 255, sa), width=1)
                sd.line([lx, ly-spike, lx, ly+spike], fill=(255, 255, 255, sa), width=1)
                if dot_r > 2:
                    diag = int(spike * 0.6)
                    sd.line([lx-diag, ly-diag, lx+diag, ly+diag], fill=(255, 255, 255, sa // 2), width=1)

            # Rare Big Stars (Giant Flares)
            if random.random() * 100 < self.big_star_chance:
                flare = dot_r + random.randint(15, 35)
                sd.line([lx-flare, ly, lx+flare, ly], fill=(255, 255, 255, star_alpha // 4), width=1)
                sd.line([lx, ly-flare, lx, ly+flare], fill=(255, 255, 255, star_alpha // 4), width=1)

        # 6. Post-Process and Composite
        if self.glow_radius > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(radius=max(0.1, self.glow_radius * self.blur_strength)))

        layer.image.alpha_composite(scratch, dest=(bx0, by0))

        # 7. Maintain History (prevent infinite growth)
        self._prev_stars.extend(new_stars)
        if len(self._prev_stars) > 80:
            self._prev_stars = self._prev_stars[-80:]


TOOL_CLASS = ConstellationBrushTool